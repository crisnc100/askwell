"""Every ask writes exactly one audit row, including when the model gateway fails: a
replay miss, an export miss, or any other provider error. The API status and CLI exit
code stay as they were."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select
from typer.testing import CliRunner

from askwell.api import create_app
from askwell.cli import app as cli_app
from askwell.config import Settings
from askwell.core.audit import AuditLog, ask_log
from askwell.llm.budget import BudgetGuard
from askwell.llm.gateway import Gateway
from askwell.llm.pricing import ModelPrice
from askwell.llm.replay import ReplayStore
from askwell.llm.types import RawResponse
from askwell.pipeline.service import AskService, SchemaConfig


def _gateway(mode: str, tmp_path: Path, transport: Any = None) -> Gateway:
    live = mode in ("live", "record")
    return Gateway(
        mode=mode,  # type: ignore[arg-type]
        store=ReplayStore(tmp_path / "empty.jsonl"),
        transport=transport,
        price_lookup=lambda _m: ModelPrice(0.0, 0.0) if live else None,
        guard=BudgetGuard(1.0) if live else None,
        max_tokens=100,
        pending_dir=tmp_path / "pending",
    )


def _rows(engine: Engine) -> list[dict[str, Any]]:
    with engine.connect() as conn:
        return [dict(r) for r in conn.execute(select(ask_log)).mappings()]


def _service(
    settings: Settings, schemas: dict[str, SchemaConfig], gateway: Gateway, audit_engine: Engine
) -> AskService:
    return AskService(settings, schemas, gateway, AuditLog(audit_engine), model="m")


@pytest.mark.parametrize(("mode", "reason"), [("replay", "replay"), ("export", "export")])
def test_a_gateway_miss_over_http_is_409_with_one_audit_row(
    mode: str,
    reason: str,
    settings: Settings,
    fieldservice_config: dict[str, SchemaConfig],
    tmp_path: Path,
    audit_engine: Engine,
) -> None:
    service = _service(settings, fieldservice_config, _gateway(mode, tmp_path), audit_engine)
    with TestClient(create_app(service)) as client:
        response = client.post("/ask", json={"schema_id": "fieldservice", "question": "q"})
    assert response.status_code == 409
    rows = _rows(audit_engine)
    assert len(rows) == 1
    assert rows[0]["outcome"] == "error"
    assert rows[0]["sql"] is None
    assert reason in rows[0]["validation"]


@pytest.mark.parametrize(("mode", "exit_code"), [("replay", 4), ("export", 3)])
def test_a_gateway_miss_in_the_cli_keeps_its_exit_code_and_audits(
    mode: str,
    exit_code: int,
    settings: Settings,
    fieldservice_config: dict[str, SchemaConfig],
    tmp_path: Path,
    audit_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _service(settings, fieldservice_config, _gateway(mode, tmp_path), audit_engine)
    monkeypatch.setattr(AskService, "from_settings", classmethod(lambda cls, *a, **k: service))
    result = CliRunner().invoke(cli_app, ["ask", "q", "--mode", mode])
    assert result.exit_code == exit_code, result.output
    rows = _rows(audit_engine)
    assert [r["outcome"] for r in rows] == ["error"]


def test_a_provider_error_is_audited_with_the_spend_so_far(
    settings: Settings,
    fieldservice_config: dict[str, SchemaConfig],
    tmp_path: Path,
    audit_engine: Engine,
) -> None:
    class Failing:
        def __init__(self) -> None:
            self.calls = 0

        def __call__(self, **_: Any) -> RawResponse:
            self.calls += 1
            if self.calls == 1:  # a paid, unparseable first answer
                return RawResponse(content="not an intent", usage={"cost": 0.02}, model="m")
            raise RuntimeError("provider exploded")

    service = _service(
        settings, fieldservice_config, _gateway("live", tmp_path, Failing()), audit_engine
    )
    with TestClient(create_app(service), raise_server_exceptions=False) as client:
        response = client.post("/ask", json={"schema_id": "fieldservice", "question": "q"})
    assert response.status_code == 500
    rows = _rows(audit_engine)
    assert len(rows) == 1
    assert rows[0]["outcome"] == "error"
    assert rows[0]["cost_usd"] == pytest.approx(0.02)
    assert "RuntimeError" in rows[0]["validation"]
