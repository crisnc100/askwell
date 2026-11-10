"""One audit row per ask, whatever fails: setup (registry, database) or a write after the
budget was charged. The row's cost is what the ask's budget guard was charged."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select

from ledgerline.api import create_app
from ledgerline.config import Settings
from ledgerline.core.audit import AuditLog, ask_log
from ledgerline.llm.budget import BudgetGuard
from ledgerline.llm.gateway import Gateway
from ledgerline.llm.pricing import ModelPrice
from ledgerline.llm.replay import ReplayStore
from ledgerline.llm.types import RawResponse
from ledgerline.pipeline.service import AskService, SchemaConfig
from tests.core.conftest import FIELDSERVICE_REGISTRY
from tests.pipeline.conftest import ScriptedGateway

UNPAID = {
    "intent_type": "summary",
    "entity": "invoices",
    "metrics": [{"agg": "count"}],
    "filters": [{"field": "status", "op": "eq", "value": "unpaid"}],
}


def _rows(engine: Engine) -> list[dict[str, Any]]:
    with engine.connect() as conn:
        return [dict(r) for r in conn.execute(select(ask_log)).mappings()]


def _post(service: AskService) -> int:
    with TestClient(create_app(service), raise_server_exceptions=False) as client:
        return client.post("/ask", json={"schema_id": "fs", "question": "q"}).status_code


def test_a_missing_sqlite_file_is_audited(
    settings: Settings, tmp_path: Path, audit_engine: Engine
) -> None:
    schemas = {
        "fs": SchemaConfig(
            "fs", "fs", FIELDSERVICE_REGISTRY, f"sqlite:///{tmp_path / 'gone.sqlite'}"
        )
    }
    service = AskService(
        settings,
        schemas,
        ScriptedGateway([UNPAID]),  # type: ignore[arg-type]
        AuditLog(audit_engine),
        model="m",
    )
    assert _post(service) == 500
    rows = _rows(audit_engine)
    assert len(rows) == 1
    assert rows[0]["outcome"] == "error"
    assert rows[0]["schema_id"] == "fs"


def test_a_missing_registry_is_audited(
    settings: Settings, sqlite_fieldservice: Engine, tmp_path: Path, audit_engine: Engine
) -> None:
    schemas = {
        "fs": SchemaConfig("fs", "fs", tmp_path / "missing.yaml", str(sqlite_fieldservice.url))
    }
    service = AskService(
        settings,
        schemas,
        ScriptedGateway([UNPAID]),  # type: ignore[arg-type]
        AuditLog(audit_engine),
        model="m",
    )
    assert _post(service) == 500
    rows = _rows(audit_engine)
    assert [r["outcome"] for r in rows] == ["error"]


class UnwritableStore(ReplayStore):
    def put(self, key: str, record: dict[str, Any]) -> None:
        raise PermissionError("recordings are read-only")


def test_a_failed_recording_write_after_the_charge_records_the_spend(
    settings: Settings, sqlite_fieldservice: Engine, tmp_path: Path, audit_engine: Engine
) -> None:
    import json

    def transport(**_: Any) -> RawResponse:
        return RawResponse(
            content=json.dumps(UNPAID), parsed=UNPAID, usage={"cost": 0.02}, model="m"
        )

    gateway = Gateway(
        mode="record",
        store=UnwritableStore(tmp_path / "s.jsonl"),
        transport=transport,
        price_lookup=lambda _m: ModelPrice(0.0, 0.0),
        guard=BudgetGuard(1.0),
        max_tokens=10,
    )
    schemas = {"fs": SchemaConfig("fs", "fs", FIELDSERVICE_REGISTRY, str(sqlite_fieldservice.url))}
    service = AskService(settings, schemas, gateway, AuditLog(audit_engine), model="m")
    assert _post(service) == 500
    rows = _rows(audit_engine)
    assert len(rows) == 1
    assert rows[0]["outcome"] == "error"
    assert rows[0]["cost_usd"] == pytest.approx(0.02)


def test_an_unreachable_audit_db_does_not_mask_the_original_error(
    settings: Settings, tmp_path: Path, audit_engine: Engine
) -> None:
    class BrokenAudit(AuditLog):
        def record(self, entry: Any) -> None:
            raise ConnectionError("audit database is down")

    schemas = {"fs": SchemaConfig("fs", "fs", tmp_path / "missing.yaml", "sqlite://")}
    service = AskService(
        settings,
        schemas,
        ScriptedGateway([UNPAID]),  # type: ignore[arg-type]
        BrokenAudit(audit_engine),
        model="m",
    )
    with pytest.raises(FileNotFoundError):
        service.ask("fs", "q")
