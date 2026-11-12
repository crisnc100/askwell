"""Grammar v0.2 beyond the named rule tests: conditional and ratio metrics, and the
date_series intent. How each validates into a plan and compiles on both engines."""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import Engine, text

from ledgerline.core.executor import run
from ledgerline.core.intent import Intent
from ledgerline.core.registry import Registry
from ledgerline.core.sqlbuild import build, compile_sql
from ledgerline.core.validate import validate
from tests.core.conftest import NOW, check
from tests.core.oracle_cases_v02 import RATIO_CASES
from tests.core.rows import normalise, same_rows


def _plan(registry: Registry, **intent: Any) -> Any:
    result = check(registry, **intent)
    assert result.ok, result.issues
    assert result.plan is not None
    return result.plan


# --- conditional metrics ---

CANCELLED = {"field": "status", "op": "eq", "value": "cancelled"}


def test_a_conditional_metric_carries_its_conditions_into_the_plan(registry: Registry) -> None:
    plan = _plan(
        registry,
        intent_type="summary",
        entity="work_orders",
        metrics=[
            {"agg": "count", "alias": "cancelled", "where": [CANCELLED]},
            {"agg": "count", "alias": "total"},
        ],
    )
    cancelled, total = plan.metrics
    assert [p.values for p in cancelled.where] == [("cancelled",)]
    assert total.where == ()
    assert plan.where == ()


@pytest.mark.parametrize(
    ("condition", "code"),
    [
        ({"field": "users.email", "op": "eq", "value": "x"}, "hidden_field"),
        ({"field": "status", "op": "eq", "value": "lost"}, "value_not_allowed"),
        ({"field": "status", "op": "gt", "value": "open"}, "operator_type"),
        ({"field": "labor_hours", "op": "eq", "value": "many"}, "value_type"),
        ({"field": "work_order_parts.quantity", "op": "gt", "value": 1}, "fan_out"),
        ({"field": "mileage", "op": "eq", "value": 1}, "unknown_field"),
        ({"field": "status", "op": "in", "values": []}, "empty_in"),
    ],
)
def test_metric_conditions_follow_every_filter_rule(
    registry: Registry, condition: dict[str, Any], code: str
) -> None:
    result = check(
        registry,
        intent_type="summary",
        entity="work_orders",
        metrics=[{"agg": "count", "where": [condition]}],
    )
    assert result.codes == [code]


def test_metric_conditions_respect_filterable(registry: Registry) -> None:
    from tests.core.test_validate import with_field

    locked = with_field(registry, "work_orders", "status", filterable=False)
    result = check(
        locked,
        intent_type="summary",
        entity="work_orders",
        metrics=[{"agg": "count", "where": [CANCELLED]}],
    )
    assert result.codes == ["not_filterable"]


@pytest.mark.parametrize("engine_name", ["postgresql", "sqlite"])
def test_conditional_metric_values_are_bound(
    engine_name: str, registry: Registry, pg_seeded: Engine, sqlite_ro: Engine
) -> None:
    plan = _plan(
        registry,
        intent_type="summary",
        entity="work_orders",
        metrics=[
            {"agg": "count", "alias": "dropped", "where": [CANCELLED]},
            {
                "agg": "sum",
                "field": "labor_hours",
                "alias": "rush_hours",
                "where": [{"field": "priority", "op": "eq", "value": "urgent"}],
            },
        ],
    )
    sql, params = compile_sql(build(plan), engine_name)
    assert "cancelled" not in sql
    assert "urgent" not in sql
    assert sorted(params.values()) == ["cancelled", "urgent"]
    assert "CASE WHEN" in sql
    engine = pg_seeded if engine_name == "postgresql" else sqlite_ro
    rows = run(engine, build(plan)).rows
    assert rows[0][0] > 0


@pytest.mark.parametrize("engine_name", ["postgresql", "sqlite"])
def test_a_metric_condition_never_drops_rows_from_other_metrics(
    engine_name: str, registry: Registry, pg_seeded: Engine, sqlite_ro: Engine
) -> None:
    """A condition on a joined table must not turn the join into an inner join:
    work orders with no technician still count in the total."""
    engine = pg_seeded if engine_name == "postgresql" else sqlite_ro
    total = _plan(registry, intent_type="summary", entity="work_orders", metrics=[{"agg": "count"}])
    both = _plan(
        registry,
        intent_type="summary",
        entity="work_orders",
        metrics=[
            {"agg": "count", "alias": "total"},
            {
                "agg": "count",
                "alias": "senior",
                "where": [{"field": "technicians.skill_level", "op": "eq", "value": "senior"}],
            },
        ],
    )
    sql, _ = compile_sql(build(both), engine_name)
    assert "LEFT OUTER JOIN" in sql
    assert run(engine, build(both)).rows[0][0] == run(engine, build(total)).rows[0][0]


def test_conditional_count_distinct(registry: Registry, sqlite_ro: Engine) -> None:
    plan = _plan(
        registry,
        intent_type="summary",
        entity="work_orders",
        metrics=[
            {
                "agg": "count_distinct",
                "field": "site_id",
                "alias": "sites_with_urgent",
                "where": [{"field": "priority", "op": "eq", "value": "urgent"}],
            }
        ],
    )
    sql, _ = compile_sql(build(plan), "sqlite")
    assert "count(DISTINCT CASE WHEN" in sql


def test_conditional_metric_in_intent_json_round_trips() -> None:
    intent = Intent.model_validate(
        {
            "intent_type": "summary",
            "entity": "work_orders",
            "metrics": [{"agg": "count", "where": [CANCELLED]}],
        }
    )
    assert intent.metrics[0].where[0].value == "cancelled"


# --- ratio metrics ---

TOTAL = {"agg": "count", "alias": "total"}
DONE = {
    "agg": "count",
    "alias": "done",
    "where": [{"field": "status", "op": "eq", "value": "completed"}],
}


def _share(**extra: Any) -> dict[str, Any]:
    return {"agg": "ratio", "alias": "share", "numerator": "done", "denominator": "total", **extra}


def test_a_ratio_names_its_parts_in_the_plan(registry: Registry) -> None:
    plan = _plan(
        registry,
        intent_type="summary",
        entity="work_orders",
        metrics=[_share(as_percent=True), TOTAL, DONE],
    )
    share = plan.metrics[0]
    assert (share.agg, share.numerator, share.denominator, share.as_percent) == (
        "ratio",
        "done",
        "total",
        True,
    )
    assert [m.label for m in plan.metrics] == ["share", "total", "done"]


def test_a_ratio_without_an_alias_gets_a_default_label(registry: Registry) -> None:
    ratio = {"agg": "ratio", "numerator": "done", "denominator": "total"}
    plan = _plan(
        registry,
        intent_type="summary",
        entity="work_orders",
        metrics=[TOTAL, DONE, ratio, ratio],
    )
    assert [m.label for m in plan.metrics] == ["total", "done", "ratio", "ratio_2"]


def test_a_ratio_can_be_sorted_on_and_used_in_having(registry: Registry) -> None:
    plan = _plan(
        registry,
        intent_type="grouped_summary",
        entity="work_orders",
        metrics=[TOTAL, DONE, _share()],
        group_by=[{"field": "job_type"}],
        having=[{"metric": "share", "op": "gt", "value": 0.1}],
        order_by=[{"target": "share", "direction": "desc"}],
    )
    assert plan.having[0].metric == "share"
    assert plan.order_by[0].label == "share"


def test_a_ratio_divides_in_floating_point_and_binds_no_constants(registry: Registry) -> None:
    plan = _plan(
        registry,
        intent_type="summary",
        entity="work_orders",
        metrics=[TOTAL, DONE, _share(as_percent=True)],
    )
    for dialect in ("postgresql", "sqlite"):
        sql, params = compile_sql(build(plan), dialect)
        assert "NULLIF(" in sql.upper(), sql
        assert "AS FLOAT" in sql.upper(), sql
        assert list(params.values()) == ["completed"], (dialect, params)


@pytest.mark.parametrize("engine_name", ["postgresql", "sqlite"])
def test_a_zero_denominator_gives_null(
    engine_name: str, registry: Registry, pg_seeded: Engine, sqlite_ro: Engine
) -> None:
    engine = pg_seeded if engine_name == "postgresql" else sqlite_ro
    none = {"agg": "count", "alias": "none", "where": [{"field": "id", "op": "lt", "value": 0}]}
    plan = _plan(
        registry,
        intent_type="summary",
        entity="work_orders",
        metrics=[
            TOTAL,
            none,
            {"agg": "ratio", "alias": "r", "numerator": "total", "denominator": "none"},
        ],
    )
    total, zero, ratio = run(engine, build(plan)).rows[0]
    assert total > 0
    assert zero == 0
    assert ratio is None


# --- differential oracle ---

V02_CASES = RATIO_CASES


def test_the_v02_oracle_cases_are_named_once() -> None:
    assert len(RATIO_CASES) == 8
    assert len({case[0] for case in V02_CASES}) == len(V02_CASES)


@pytest.mark.parametrize("engine_name", ["postgresql", "sqlite"])
@pytest.mark.parametrize(
    ("case_id", "intent", "reference"), V02_CASES, ids=[case[0] for case in V02_CASES]
)
def test_v02_builder_matches_reference(
    case_id: str,
    intent: dict[str, Any],
    reference: str,
    engine_name: str,
    registry: Registry,
    pg_seeded: Engine,
    sqlite_ro: Engine,
) -> None:
    parsed = Intent.model_validate(intent)
    result = validate(parsed, registry, now=NOW)
    assert result.plan is not None, result.issues
    with pg_seeded.connect() as conn:
        expected = conn.execute(text(reference)).fetchall()
    assert expected, f"{case_id}: reference returned no rows"
    engine = pg_seeded if engine_name == "postgresql" else sqlite_ro
    got = run(engine, build(result.plan)).rows
    ordered = bool(parsed.order_by)
    assert same_rows(got, expected, ordered), (
        f"{case_id} on {engine_name}\n got: {normalise(got, ordered)[:5]}\n"
        f"want: {normalise(expected, ordered)[:5]}"
    )
