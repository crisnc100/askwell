"""The ask graph with a scripted test-double gateway: success, retry-then-success,
two failures, unanswerable, parse errors, and the audit row for every outcome."""

from __future__ import annotations

from typing import Any

from sqlalchemy import Engine, select

from askwell.config import Settings
from askwell.core.audit import ask_log
from askwell.pipeline.service import SchemaConfig
from tests.pipeline.conftest import scripted_service

UNPAID = {
    "intent_type": "summary",
    "entity": "invoices",
    "metrics": [{"agg": "count"}],
    "filters": [{"field": "status", "op": "eq", "value": "unpaid"}],
}


def _audit(engine: Engine) -> list[dict[str, Any]]:
    with engine.connect() as conn:
        return [dict(r) for r in conn.execute(select(ask_log)).mappings()]


def test_answerable_question(
    settings: Settings, fieldservice_config: dict[str, SchemaConfig], audit_engine: Engine
) -> None:
    service, gateway = scripted_service(settings, fieldservice_config, [UNPAID], audit_engine)
    result = service.ask("fieldservice", "How many invoices are unpaid?")
    assert result.refusal is None
    assert result.columns == ["count"]
    assert result.rows == [[161]]
    assert result.sql is not None
    assert "unpaid" not in result.sql
    assert list((result.params or {}).values()) == ["unpaid"]
    assert len(gateway.calls) == 1
    assert result.validation["ok"]
    rows = _audit(audit_engine)
    assert [(r["outcome"], r["row_count"], r["trace_id"]) for r in rows] == [
        ("answered", 1, result.trace_id)
    ]


def test_retry_then_success(
    settings: Settings, fieldservice_config: dict[str, SchemaConfig], audit_engine: Engine
) -> None:
    bad = {**UNPAID, "filters": [{"field": "status", "op": "eq", "value": "outstanding"}]}
    service, gateway = scripted_service(settings, fieldservice_config, [bad, UNPAID], audit_engine)
    result = service.ask("fieldservice", "How many invoices are outstanding?")
    assert result.refusal is None
    assert result.rows == [[161]]
    attempts = result.validation["attempts"]
    assert [a["issues"][0]["code"] if a["issues"] else None for a in attempts] == [
        "value_not_allowed",
        None,
    ]
    retry = gateway.calls[1]
    assert retry[-2].role == "assistant"
    assert "value_not_allowed" in retry[-1].content
    assert result.cost_usd == 0.002


def test_two_failures_become_a_refusal(
    settings: Settings, fieldservice_config: dict[str, SchemaConfig], audit_engine: Engine
) -> None:
    bad = {"intent_type": "row_list", "entity": "users", "select": ["email"]}
    service, _ = scripted_service(settings, fieldservice_config, [bad, bad], audit_engine)
    result = service.ask("fieldservice", "List user emails.")
    assert result.sql is None
    assert result.rows == []
    assert result.refusal == "no valid query after 2 attempts (hidden_field)"
    assert _audit(audit_engine)[0]["outcome"] == "refused"


def test_unanswerable_is_a_refusal_with_its_reason(
    settings: Settings, fieldservice_config: dict[str, SchemaConfig], audit_engine: Engine
) -> None:
    answer = {"intent_type": "unanswerable", "unanswerable_reason": "no marketing data"}
    service, gateway = scripted_service(settings, fieldservice_config, [answer], audit_engine)
    result = service.ask("fieldservice", "Marketing spend?")
    assert result.refusal == "no marketing data"
    assert result.sql is None
    assert len(gateway.calls) == 1
    row = _audit(audit_engine)[0]
    assert row["outcome"] == "refused"
    assert row["sql"] is None


def test_parse_errors_are_retried_then_refused(
    settings: Settings, fieldservice_config: dict[str, SchemaConfig], audit_engine: Engine
) -> None:
    service, gateway = scripted_service(
        settings, fieldservice_config, ["Sure! SELECT 1", "still not json"], audit_engine
    )
    result = service.ask("fieldservice", "q")
    assert result.refusal is not None
    assert result.refusal.startswith("could not read the model's answer")
    assert "not a valid intent" in gateway.calls[1][-1].content
    parse_then_ok, _ = scripted_service(
        settings, fieldservice_config, ["nope", UNPAID], audit_engine
    )
    assert parse_then_ok.ask("fieldservice", "q").rows == [[161]]


def test_execution_errors_become_refusals_and_are_audited(
    settings: Settings, fieldservice_config: dict[str, SchemaConfig], audit_engine: Engine
) -> None:
    slow = settings.model_copy(update={"query_timeout_s": 0.0})
    service, _ = scripted_service(slow, fieldservice_config, [UNPAID], audit_engine)
    big = {
        "intent_type": "row_list",
        "entity": "work_order_parts",
        "select": ["work_orders.status", "parts.name"],
        "limit": 1000,
    }
    service.gateway.answers = [big]  # type: ignore[attr-defined]
    result = service.ask("fieldservice", "q")
    assert result.refusal is not None
    assert result.refusal.startswith("the query failed")
    assert _audit(audit_engine)[0]["outcome"] == "error"


def test_rows_are_never_sent_to_the_model(
    settings: Settings, fieldservice_config: dict[str, SchemaConfig], audit_engine: Engine
) -> None:
    listing = {"intent_type": "row_list", "entity": "customers", "select": ["name"], "limit": 3}
    service, gateway = scripted_service(settings, fieldservice_config, [listing], audit_engine)
    result = service.ask("fieldservice", "Name three customers.")
    sent = " ".join(m.content for call in gateway.calls for m in call)
    for (name,) in result.rows:
        assert name not in sent


def test_each_attempt_keeps_its_own_provenance(
    settings: Settings, fieldservice_config: dict[str, SchemaConfig], audit_engine: Engine
) -> None:
    from askwell.core.intent import Intent
    from askwell.llm.types import LLMResult, RawResponse

    bad = {**UNPAID, "filters": [{"field": "status", "op": "eq", "value": "outstanding"}]}
    service, gateway = scripted_service(settings, fieldservice_config, [bad, UNPAID], audit_engine)
    marks = iter([{"simulated_by": "sim-A", "standing_in_for": "t"}, None])
    original = gateway.complete

    def with_provenance(**kw: Any) -> LLMResult[Intent]:
        result = original(**kw)
        return result.model_copy(update={"provenance": next(marks)})

    gateway.complete = with_provenance  # type: ignore[method-assign]
    _ = RawResponse
    result = service.ask("fieldservice", "q")
    attempts = result.validation["attempts"]
    assert attempts[0]["provenance"] == {"simulated_by": "sim-A", "standing_in_for": "t"}
    assert attempts[1]["provenance"] is None
