"""Spend on a failed attempt is still spend: it reaches cost_usd and the audit row."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlalchemy import Engine, select

from askwell.config import Settings
from askwell.core.audit import AuditLog, ask_log
from askwell.llm.budget import BudgetGuard
from askwell.llm.gateway import Gateway
from askwell.llm.pricing import ModelPrice
from askwell.llm.replay import ReplayStore
from askwell.llm.types import RawResponse
from askwell.pipeline.service import AskService, SchemaConfig

UNPAID = (
    '{"intent_type": "summary", "entity": "invoices", "metrics": [{"agg": "count"}], '
    '"filters": [{"field": "status", "op": "eq", "value": "unpaid"}]}'
)


class Transport:
    def __init__(self, contents: list[str]) -> None:
        self.contents = list(contents)

    def __call__(self, **_: Any) -> RawResponse:
        return RawResponse(content=self.contents.pop(0), usage={"cost": 0.01}, model="m")


def _service(
    settings: Settings,
    schemas: dict[str, SchemaConfig],
    tmp_path: Path,
    contents: list[str],
    audit_engine: Engine,
) -> AskService:
    gateway = Gateway(
        mode="live",
        store=ReplayStore(tmp_path / "s.jsonl"),
        transport=Transport(contents),
        price_lookup=lambda _m: ModelPrice(1e-9, 1e-9),
        guard=BudgetGuard(1.0),
        max_tokens=10,
    )
    return AskService(settings, schemas, gateway, AuditLog(audit_engine), model="m")


def test_a_parse_failure_then_success_costs_both_calls(
    settings: Settings,
    fieldservice_config: dict[str, SchemaConfig],
    tmp_path: Path,
    audit_engine: Engine,
) -> None:
    service = _service(settings, fieldservice_config, tmp_path, ["not json", UNPAID], audit_engine)
    result = service.ask("fieldservice", "How many invoices are unpaid?")
    assert result.rows == [[161]]
    assert result.cost_usd == 0.02
    with audit_engine.connect() as conn:
        assert conn.execute(select(ask_log.c.cost_usd)).scalar_one() == 0.02


def test_two_parse_failures_cost_both_calls(
    settings: Settings,
    fieldservice_config: dict[str, SchemaConfig],
    tmp_path: Path,
    audit_engine: Engine,
) -> None:
    service = _service(
        settings, fieldservice_config, tmp_path, ["nope", "still nope"], audit_engine
    )
    result = service.ask("fieldservice", "q")
    assert result.refusal is not None
    assert result.cost_usd == 0.02
    with audit_engine.connect() as conn:
        assert conn.execute(select(ask_log.c.cost_usd)).scalar_one() == 0.02


def test_a_oneshot_parse_failure_keeps_its_cost(
    sqlite_fieldservice: Engine, tmp_path: Path
) -> None:
    from askwell.bench.items import EvalItem
    from askwell.bench.systems import OneShotSystem
    from askwell.core.registry import load_registry
    from tests.core.conftest import FIELDSERVICE_REGISTRY

    gateway = Gateway(
        mode="live",
        store=ReplayStore(tmp_path / "s.jsonl"),
        transport=Transport(["prose"]),
        price_lookup=lambda _m: ModelPrice(1e-9, 1e-9),
        guard=BudgetGuard(1.0),
        max_tokens=10,
    )
    system = OneShotSystem(
        gateway,
        sqlite_fieldservice,
        load_registry(FIELDSERVICE_REGISTRY),
        "m",
        "2026-06-30",
        1000,
        5.0,
    )
    item = EvalItem("x", "fieldservice", "in_schema", "q", "SELECT 1", False, "easy")
    answer = system.answer(item, 1, None)
    assert answer.error is not None
    assert answer.cost_usd == 0.01
