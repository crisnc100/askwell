"""Grammar v0.3 (PR-3): computed values, durations, has / has none, and comparison with
an aggregate. The builder's rows on Postgres and on SQLite must equal a hand-written
reference query; every value stays a bound parameter; each switch off refuses."""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import Engine, text

from askwell.core.executor import run
from askwell.core.features import ALL
from askwell.core.intent import Intent
from askwell.core.registry import Registry
from askwell.core.sqlbuild import build, compile_sql
from askwell.core.validate import ValidationResult, validate
from tests.core.conftest import NOW
from tests.core.oracle_cases_v03 import CASES
from tests.core.rows import normalise, same_rows

IDS = [case[0] for case in CASES]


def _check(
    registry: Registry, intent: dict[str, Any], features: frozenset[str] = ALL
) -> ValidationResult:
    return validate(Intent.model_validate(intent), registry, now=NOW, features=features)


@pytest.mark.parametrize("engine_name", ["postgresql", "sqlite"])
@pytest.mark.parametrize(("case_id", "intent", "reference", "may_be_empty"), CASES, ids=IDS)
def test_builder_matches_reference(
    case_id: str,
    intent: dict[str, Any],
    reference: str,
    may_be_empty: bool,
    engine_name: str,
    registry: Registry,
    pg_seeded: Engine,
    sqlite_ro: Engine,
) -> None:
    result = _check(registry, intent)
    assert result.plan is not None, result.issues
    with pg_seeded.connect() as conn:
        expected = conn.execute(text(reference)).fetchall()
    assert bool(expected) != may_be_empty, f"{case_id}: reference rows {len(expected)}"
    engine = pg_seeded if engine_name == "postgresql" else sqlite_ro
    got = run(engine, build(result.plan)).rows
    ordered = bool(intent.get("order_by"))
    assert same_rows(got, expected, ordered), (
        f"{case_id} on {engine_name}\n got: {normalise(got, ordered)[:5]}\n"
        f"want: {normalise(expected, ordered)[:5]}"
    )


# --- every value is bound, never written into the SQL (P3.3) ---

SENTINEL = "zz_sentinel_9137"


@pytest.mark.parametrize("dialect", ["postgresql", "sqlite"])
def test_values_in_new_slots_are_bound(registry: Registry, dialect: str) -> None:
    intents: list[dict[str, Any]] = [
        {
            "intent_type": "summary",
            "entity": "customers",
            "metrics": [{"agg": "count"}],
            "filters": [
                {"has": "sites", "where": [{"field": "name", "op": "eq", "value": SENTINEL}]}
            ],
        },
        {
            "intent_type": "summary",
            "entity": "invoices",
            "metrics": [{"agg": "count"}],
            "filters": [
                {"field": "amount", "op": "lt", "value": 913_791_379},
                {"field": "amount", "op": "gt", "value": {"of": "avg"}},
            ],
        },
        {
            "intent_type": "summary",
            "entity": "work_order_parts",
            "metrics": [{"agg": "count"}],
            "filters": [
                {
                    "field": {"op": "multiply", "left": "quantity", "right": "parts.unit_price"},
                    "op": "gt",
                    "value": 913_791_379,
                },
                {"field": "parts.name", "op": "eq", "value": SENTINEL},
            ],
        },
    ]
    for intent in intents:
        result = _check(registry, intent)
        assert result.plan is not None, result.issues
        sql, params = compile_sql(build(result.plan), dialect)
        assert SENTINEL not in sql
        assert "913791379" not in sql
        assert SENTINEL in params.values() or 913_791_379 in params.values()
    now_plan = _check(
        registry,
        {
            "intent_type": "summary",
            "entity": "invoices",
            "metrics": [{"agg": "avg", "field": {"days_between": ["issued_at", "now"]}}],
        },
    ).plan
    assert now_plan is not None
    sql, params = compile_sql(build(now_plan), dialect)
    assert "2026" not in sql
    assert any(str(v).startswith("2026-06-30") for v in params.values())


# --- each switch off refuses (P2.5 for PR-3's features) ---

OFF_CASES: list[tuple[str, dict[str, Any]]] = [
    (
        "computed",
        {
            "intent_type": "summary",
            "entity": "work_order_parts",
            "metrics": [
                {
                    "agg": "sum",
                    "field": {"op": "multiply", "left": "quantity", "right": "parts.unit_price"},
                }
            ],
        },
    ),
    (
        "durations",
        {
            "intent_type": "summary",
            "entity": "work_orders",
            "metrics": [{"agg": "avg", "field": {"days_between": ["opened_at", "completed_at"]}}],
        },
    ),
    (
        "has",
        {
            "intent_type": "summary",
            "entity": "technicians",
            "metrics": [{"agg": "count"}],
            "filters": [{"has": "work_orders", "none": True}],
        },
    ),
    (
        "vs_aggregate",
        {
            "intent_type": "summary",
            "entity": "invoices",
            "metrics": [{"agg": "count"}],
            "filters": [{"field": "amount", "op": "gt", "value": {"of": "avg"}}],
        },
    ),
]


@pytest.mark.parametrize(("feature", "intent"), OFF_CASES, ids=[c[0] for c in OFF_CASES])
def test_each_switch_off_refuses(registry: Registry, feature: str, intent: dict[str, Any]) -> None:
    assert _check(registry, intent).ok
    assert _check(registry, intent, ALL - {feature}).codes == ["feature_off"]


# --- shapes ---


def test_computed_labels_and_order(registry: Registry) -> None:
    plan = _check(
        registry,
        {
            "intent_type": "row_list",
            "entity": "parts",
            "select": [{"op": "subtract", "left": "unit_price", "right": "unit_cost"}],
        },
    ).plan
    assert plan is not None
    assert plan.select[0].label == "unit_price_minus_unit_cost"


def test_a_has_filter_names_the_link_when_two_point_back(registry: Registry) -> None:
    intent = {
        "intent_type": "summary",
        "entity": "work_orders",
        "metrics": [{"agg": "count"}],
        "filters": [{"has": "invoices@work_order_id"}],
    }
    assert _check(registry, intent).ok
    wrong = {**intent, "filters": [{"has": "invoices@issued_at"}]}
    assert _check(registry, wrong).codes == ["has_link"]


def test_a_two_link_has_needs_the_link_named() -> None:
    from tests.core.conftest import make_registry

    reg = make_registry(
        {"flights": ["origin_id", "dest_id"], "airports": ["elevation"]},
        [("flights", "origin_id", "airports", "id"), ("flights", "dest_id", "airports", "id")],
    )
    base = {"intent_type": "summary", "entity": "airports", "metrics": [{"agg": "count"}]}
    assert _check(reg, {**base, "filters": [{"has": "flights"}]}).codes == ["ambiguous_path"]
    assert _check(reg, {**base, "filters": [{"has": "flights@origin_id"}]}).ok


def test_aggregate_comparison_scope_rules(registry: Registry) -> None:
    above = {"field": "labor_hours", "op": "gt", "value": {"of": "avg"}}
    base = {"entity": "work_orders", "metrics": [{"agg": "count"}]}
    grouped = {
        **base,
        "intent_type": "grouped_summary",
        "group_by": [{"field": "job_type"}],
        "filters": [above],
    }
    assert _check(registry, grouped).codes == ["vs_aggregate_scope"]
    joined = {
        **base,
        "intent_type": "summary",
        "filters": [above, {"field": "technicians.skill_level", "op": "eq", "value": "senior"}],
    }
    assert _check(registry, joined).codes == ["vs_aggregate_scope"]
    in_group = {**base, "intent_type": "summary", "filters": [{"any_of": [above]}]}
    assert _check(registry, in_group).codes == ["vs_aggregate_scope"]
    on_join = {
        **base,
        "intent_type": "summary",
        "filters": [{"field": "technicians.hourly_rate", "op": "gt", "value": {"of": "avg"}}],
    }
    assert _check(registry, on_join).codes == ["vs_aggregate_scope"]


@pytest.mark.parametrize(
    "code", ["feature_off", "computed_type", "duration_type", "has_link", "vs_aggregate_scope"]
)
def test_every_new_code_has_plain_text(code: str) -> None:
    from askwell.workspace.ask import _GENERAL, explain

    result = {
        "refusal": "the intent failed validation twice",
        "intent": {"intent_type": "summary"},
        "validation": {"ok": False, "attempts": [{"issues": [{"code": code, "message": "m"}]}]},
    }
    explanation = explain(result)
    assert explanation is not None
    assert explanation["message"] != _GENERAL[0]
    assert code not in explanation["message"] + explanation["suggestion"]
