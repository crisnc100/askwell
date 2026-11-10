"""A budget stop during an ask is a refusal with an audit row, not an HTTP 500."""

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
from ledgerline.llm.errors import BudgetExceededError
from ledgerline.llm.gateway import Gateway
from ledgerline.llm.pricing import ModelPrice
from ledgerline.llm.replay import ReplayStore
from ledgerline.llm.types import RawResponse
from ledgerline.pipeline.service import AskService, SchemaConfig


class Malformed:
    """Every answer is unparseable and costs $0.03, so the first attempt is paid and the
    retry's $0.03 worst case no longer fits a $0.05 limit."""

    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, **_: Any) -> RawResponse:
        self.calls += 1
        return RawResponse(content="not an intent", usage={"cost": 0.03}, model="m")


def _service(
    settings: Settings, schemas: dict[str, SchemaConfig], tmp_path: Path, audit_engine: Engine
) -> tuple[AskService, Malformed]:
    transport = Malformed()
    gateway = Gateway(
        mode="live",
        store=ReplayStore(tmp_path / "s.jsonl"),
        transport=transport,
        # Worst case per call = 1000 completion tokens x $0.00003 = $0.03.
        price_lookup=lambda _m: ModelPrice(0.0, 0.00003),
        guard=BudgetGuard(1.0),
        max_tokens=1000,
    )
    limited = settings.model_copy(update={"ask_budget_usd": 0.05})
    return AskService(limited, schemas, gateway, AuditLog(audit_engine), model="m"), transport


def test_a_budget_stop_on_retry_is_a_refusal_with_one_audit_row(
    settings: Settings,
    fieldservice_config: dict[str, SchemaConfig],
    tmp_path: Path,
    audit_engine: Engine,
) -> None:
    service, transport = _service(settings, fieldservice_config, tmp_path, audit_engine)
    with TestClient(create_app(service)) as client:
        response = client.post("/ask", json={"schema_id": "fieldservice", "question": "q"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["refusal"] == "this question hit the spending limit"
    assert body["sql"] is None
    assert body["cost_usd"] == pytest.approx(0.03)
    assert transport.calls == 1  # the retry was stopped before it was sent
    with audit_engine.connect() as conn:
        rows = conn.execute(select(ask_log)).mappings().all()
    assert len(rows) == 1
    assert rows[0]["outcome"] == "refused"
    assert rows[0]["cost_usd"] == pytest.approx(0.03)
    assert "spending limit" in rows[0]["validation"]


def test_a_budget_stop_on_the_first_attempt_is_a_refusal_too(
    settings: Settings,
    fieldservice_config: dict[str, SchemaConfig],
    tmp_path: Path,
    audit_engine: Engine,
) -> None:
    service, transport = _service(settings, fieldservice_config, tmp_path, audit_engine)
    service.settings = service.settings.model_copy(update={"ask_budget_usd": 0.01})
    result = service.ask("fieldservice", "q")
    assert result.refusal == "this question hit the spending limit"
    assert result.cost_usd == 0.0
    assert transport.calls == 0
    with audit_engine.connect() as conn:
        rows = conn.execute(select(ask_log.c.outcome, ask_log.c.cost_usd)).all()
    assert [(r[0], r[1]) for r in rows] == [("refused", 0.0)]


def test_an_eval_run_still_stops_on_its_shared_budget(
    settings: Settings,
    fieldservice_config: dict[str, SchemaConfig],
    tmp_path: Path,
    audit_engine: Engine,
) -> None:
    """The eval shares one run-wide guard and must abort, not record a refusal."""
    service, _ = _service(settings, fieldservice_config, tmp_path, audit_engine)
    service.reset_budget_per_ask = False
    service.gateway.guard = BudgetGuard(0.01)
    with pytest.raises(BudgetExceededError):
        service.ask("fieldservice", "q")
