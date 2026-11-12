"""Grammar v0.2 beyond the named rule tests: conditional and ratio metrics, and the
date_series intent. How each validates into a plan and compiles on both engines."""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import Engine, text

from askwell.core.executor import run
from askwell.core.intent import Intent
from askwell.core.registry import Registry
from askwell.core.sqlbuild import build, compile_sql
from askwell.core.validate import validate
from tests.core.conftest import NOW, check
from tests.core.oracle_cases_v02 import ORDER_CASES, RATIO_CASES, SERIES_CASES
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


# --- date series ---

OPENED = {"metric": {"agg": "count"}, "date_field": "opened_at", "alias": "opened"}
URGENT_INSTALLS = [
    {"field": "priority", "op": "eq", "value": "urgent"},
    {"field": "job_type", "op": "eq", "value": "installation"},
]


def _weekly(second: dict[str, Any]) -> dict[str, Any]:
    return {
        "intent_type": "date_series",
        "entity": "work_orders",
        "grain": "iso_week",
        "date_range": {"start": "2025-01-06", "end": "2025-04-07"},
        "series": [OPENED, second],
    }


def test_a_series_plan_holds_each_series_with_its_own_date_field(registry: Registry) -> None:
    plan = _plan(
        registry,
        **_weekly(
            {
                "metric": {"agg": "count"},
                "date_field": "completed_at",
                "where": URGENT_INSTALLS,
                "alias": "urgent",
            }
        ),
    )
    assert plan.intent_type == "date_series"
    assert plan.grain == "iso_week"
    assert plan.metrics == ()
    opened, urgent = plan.series
    assert (opened.label, opened.date_field.name) == ("opened", "opened_at")
    assert (urgent.label, urgent.date_field.name) == ("urgent", "completed_at")
    # The period applies to each series by its own date field.
    assert {p.field.name for p in opened.where} == {"opened_at"}
    assert {p.field.name for p in urgent.where} == {"priority", "job_type", "completed_at"}


@pytest.mark.parametrize("engine_name", ["postgresql", "sqlite"])
def test_an_empty_period_is_zero_for_a_count_and_null_for_a_sum(
    engine_name: str, registry: Registry, pg_seeded: Engine, sqlite_ro: Engine
) -> None:
    engine = pg_seeded if engine_name == "postgresql" else sqlite_ro
    plan = _plan(
        registry,
        **{
            **_weekly(OPENED),
            "series": [
                OPENED,
                {
                    "metric": {"agg": "count"},
                    "date_field": "completed_at",
                    "where": URGENT_INSTALLS,
                    "alias": "n_urgent",
                },
                {
                    "metric": {"agg": "sum", "field": "labor_hours"},
                    "date_field": "completed_at",
                    "where": URGENT_INSTALLS,
                    "alias": "urgent_hours",
                },
            ],
        },
    )
    result = run(engine, build(plan))
    assert result.columns == ["period", "opened", "n_urgent", "urgent_hours"]
    rows = result.rows
    assert len(rows) == 13
    assert [r[0] for r in rows] == sorted(r[0] for r in rows)
    empty = [r for r in rows if r[2] == 0]
    assert empty, rows
    assert all(r[3] is None for r in empty)
    assert all(r[3] is not None for r in rows if r[2] > 0)


def test_a_one_series_intent_is_ordered_by_period(registry: Registry, sqlite_ro: Engine) -> None:
    plan = _plan(
        registry,
        intent_type="date_series",
        entity="work_orders",
        grain="quarter",
        series=[OPENED],
    )
    rows = run(sqlite_ro, build(plan)).rows
    assert [r[0] for r in rows] == sorted(r[0] for r in rows)
    assert sum(r[1] for r in rows) == 5000


def test_series_skip_rows_without_their_date(registry: Registry, sqlite_ro: Engine) -> None:
    """A row with no date in one series belongs to no period, so no NULL period row."""
    plan = _plan(
        registry,
        intent_type="date_series",
        entity="work_orders",
        grain="year",
        series=[
            OPENED,
            {"metric": {"agg": "count"}, "date_field": "completed_at", "alias": "completed"},
        ],
    )
    rows = run(sqlite_ro, build(plan)).rows
    assert all(r[0] is not None for r in rows)
    assert sum(r[2] for r in rows) == 4626


@pytest.mark.parametrize("grain", ["day", "iso_week", "month", "quarter", "year"])
def test_series_grains_agree_across_engines(
    grain: str, registry: Registry, pg_seeded: Engine, sqlite_ro: Engine
) -> None:
    plan = _plan(
        registry,
        intent_type="date_series",
        entity="work_orders",
        grain=grain,
        date_range={"start": "2025-12-01", "end": "2026-03-01"},
        series=[
            OPENED,
            {"metric": {"agg": "count"}, "date_field": "scheduled_for", "alias": "scheduled"},
        ],
    )
    pg = run(pg_seeded, build(plan)).rows
    lite = run(sqlite_ro, build(plan)).rows
    assert pg
    assert same_rows(pg, lite, ordered=True)


# --- differential oracle ---

V02_CASES = RATIO_CASES + SERIES_CASES + ORDER_CASES


def test_the_v02_oracle_cases_are_named_once() -> None:
    assert len(RATIO_CASES) == 8
    assert len(SERIES_CASES) == 4
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


# --- review fixes ---


@pytest.mark.parametrize(
    "part",
    [
        {"agg": "min", "field": "opened_at", "alias": "first"},
        {"agg": "max", "field": "scheduled_for", "alias": "first"},
    ],
)
@pytest.mark.parametrize("side", ["numerator", "denominator"])
def test_a_ratio_refuses_a_date_part(registry: Registry, part: dict[str, Any], side: str) -> None:
    ratio = {"agg": "ratio", "numerator": "total", "denominator": "total", side: "first"}
    result = check(
        registry, intent_type="summary", entity="work_orders", metrics=[TOTAL, part, ratio]
    )
    assert result.codes == ["ratio_ref"]
    assert "numeric" in result.issues[0].message


def test_a_ratio_accepts_min_and_max_of_numbers(registry: Registry) -> None:
    _plan(
        registry,
        intent_type="summary",
        entity="work_orders",
        metrics=[
            {"agg": "max", "field": "labor_hours", "alias": "most"},
            {"agg": "min", "field": "labor_hours", "alias": "least"},
            {"agg": "ratio", "numerator": "most", "denominator": "least"},
        ],
    )


@pytest.mark.parametrize(
    "metric",
    [
        {"agg": "count", "distinct": True},
        {"agg": "count", "distinct": True, "where": [CANCELLED]},
    ],
)
def test_distinct_needs_a_field(registry: Registry, metric: dict[str, Any]) -> None:
    result = check(registry, intent_type="summary", entity="work_orders", metrics=[metric])
    assert result.codes == ["value_shape"]
    assert "distinct" in result.issues[0].message


@pytest.mark.parametrize("engine_name", ["postgresql", "sqlite"])
@pytest.mark.parametrize("direction", ["asc", "desc"])
def test_nulls_sort_last_in_both_directions_on_both_engines(
    engine_name: str, direction: str, registry: Registry, pg_seeded: Engine, sqlite_ro: Engine
) -> None:
    engine = pg_seeded if engine_name == "postgresql" else sqlite_ro
    plan = _plan(
        registry,
        intent_type="grouped_summary",
        entity="work_orders",
        metrics=[
            TOTAL,
            _count_where("dropped", "status", "cancelled"),
            {"agg": "ratio", "alias": "r", "numerator": "total", "denominator": "dropped"},
        ],
        group_by=[{"field": "status"}],
        order_by=[{"target": "r", "direction": direction}],
    )
    sql, _ = compile_sql(build(plan), engine_name)
    assert "NULLS LAST" in sql
    ratios = [row[3] for row in run(engine, build(plan)).rows]
    assert ratios[0] is not None
    assert ratios[1:] == [None] * (len(ratios) - 1)


def _count_where(alias: str, field: str, value: str) -> dict[str, Any]:
    return {"agg": "count", "alias": alias, "where": [{"field": field, "op": "eq", "value": value}]}
