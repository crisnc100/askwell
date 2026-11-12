"""SQL builder: values are always bound (Hypothesis sentinel property), identifiers are
the registry's, grains compile per dialect and agree across engines."""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from typing import Any

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from sqlalchemy import Date, DateTime, Engine, literal, select
from sqlalchemy.dialects import mysql
from sqlalchemy.exc import CompileError

from ledgerline.core.executor import run
from ledgerline.core.intent import Intent
from ledgerline.core.registry import Registry, load_registry
from ledgerline.core.sqlbuild import GRAINS, build, compile_sql, dialect_for
from ledgerline.core.validate import validate
from tests.core.conftest import FIELDSERVICE_REGISTRY, NOW

# --- sentinel property ---

# Text sentinels: a unique marker plus arbitrary payload, including SQL metacharacters.
_payload = st.text(
    alphabet=st.sampled_from(list("abcXYZ019 '\";-%_\\/*()=<>|&.,\n\tЖ✓")), max_size=12
)
text_sentinel = st.builds(lambda p, n: f"zqx{n}{p}", _payload, st.integers(10**5, 10**6))
# Numeric sentinels: large and unusual, so they cannot collide with SQL text such as
# LIMIT or alias suffixes. That is the sentinel design, not a narrowing.
int_sentinel = st.integers(min_value=7_000_000_001, max_value=7_999_999_999)
float_sentinel = st.floats(min_value=1e9, max_value=2e9, allow_nan=False).map(lambda f: f + 0.123)

# Free-text fields reachable many-to-one from invoices (categoricals would rightly reject
# an unknown value; parts is on the many side).
TEXT_FIELDS = ["customers.name", "sites.name", "technicians.full_name"]
NUM_FIELDS = ["amount", "work_orders.labor_hours", "technicians.hourly_rate", "id"]
BOOL_FIELDS = ["customers.is_active", "technicians.is_active"]


@st.composite
def condition(draw: st.DrawFn) -> tuple[dict[str, Any], list[Any]]:
    kind = draw(
        st.sampled_from(
            [
                "text_eq",
                "text_in",
                "ilike",
                "num_cmp",
                "num_between",
                "num_in",
                "date",
                "datetime",
                "bool",
            ]
        )
    )
    if kind == "text_eq":
        v = draw(text_sentinel)
        return {"field": draw(st.sampled_from(TEXT_FIELDS)), "op": "neq", "value": v}, [v]
    if kind == "text_in":
        vs = draw(st.lists(text_sentinel, min_size=1, max_size=3, unique=True))
        return {"field": draw(st.sampled_from(TEXT_FIELDS)), "op": "in", "values": vs}, vs
    if kind == "ilike":
        v = draw(text_sentinel)
        return {"field": draw(st.sampled_from(TEXT_FIELDS)), "op": "ilike_contains", "value": v}, [
            v
        ]
    if kind == "num_cmp":
        v = draw(st.one_of(int_sentinel, float_sentinel))
        op = draw(st.sampled_from(["eq", "neq", "gt", "gte", "lt", "lte"]))
        field = draw(st.sampled_from(NUM_FIELDS))
        if field == "id":
            v = draw(int_sentinel)
        return {"field": field, "op": op, "value": v}, [v]
    if kind == "num_between":
        lo = draw(int_sentinel)
        hi = lo + draw(st.integers(1, 10**6))
        return {"field": "amount", "op": "between", "values": [lo, hi]}, [lo, hi]
    if kind == "num_in":
        vs = draw(st.lists(int_sentinel, min_size=1, max_size=3, unique=True))
        return {"field": "id", "op": "in", "values": vs}, vs
    if kind == "datetime":
        moment = datetime(2017, 3, 9, 7, 11, 13, 123457) + timedelta(
            seconds=draw(st.integers(0, 10**8)), microseconds=draw(st.integers(1, 999_999))
        )
        op = draw(st.sampled_from(["eq", "neq", "gt", "gte", "lt", "lte"]))
        return {"field": "work_orders.opened_at", "op": op, "value": moment.isoformat()}, [moment]
    if kind == "bool":
        v = draw(st.booleans())
        field = draw(st.sampled_from(BOOL_FIELDS))
        return {"field": field, "op": draw(st.sampled_from(["eq", "neq"])), "value": v}, [v]
    days = draw(st.integers(0, 3000))
    day = date(2017, 3, 9) + timedelta(days=days)
    return {"field": "issued_at", "op": "lte", "value": day.isoformat()}, [day]


def _sql_mentions(sql: str, value: Any) -> bool:
    if isinstance(value, bool):
        # A boolean has no unique text; any TRUE/FALSE literal means one was inlined.
        # (An inlined 1/0 on SQLite is caught by the parameter count instead.)
        return re.search(r"\b(true|false)\b", sql, re.IGNORECASE) is not None
    if isinstance(value, str):
        return value in sql
    if isinstance(value, datetime):
        return value.isoformat() in sql or value.isoformat(sep=" ") in sql
    if isinstance(value, date):
        return value.isoformat() in sql
    return repr(value) in sql or str(int(value)) in sql


def _is_bound(value: Any, bound: Any) -> bool:
    if isinstance(value, bool) or isinstance(bound, bool):
        return bound is value  # True == 1 in Python; a bool must be bound as a bool
    if value == bound:
        return True
    # ilike_contains binds the value with LIKE wildcards escaped by "/" (autoescape).
    return (
        isinstance(value, str) and isinstance(bound, str) and re.sub(r"/(.)", r"\1", bound) == value
    )


@settings(max_examples=300, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(conditions=st.lists(condition(), min_size=1, max_size=4))
def test_every_filter_value_is_bound_never_inlined(
    conditions: list[tuple[dict[str, Any], list[Any]]],
) -> None:
    registry = load_registry(FIELDSERVICE_REGISTRY)
    intent = Intent.model_validate(
        {
            "intent_type": "row_list",
            "entity": "invoices",
            "select": ["id", "amount"],
            "filters": [c for c, _ in conditions],
        }
    )
    result = validate(intent, registry, now=NOW)
    assert result.plan is not None, result.issues
    stmt = build(result.plan)
    for dialect in ("postgresql", "sqlite"):
        sql, params = compile_sql(stmt, dialect)
        bound = list(params.values())
        for _, values in conditions:
            for value in values:
                assert not _sql_mentions(sql, value), (dialect, value, sql)
                assert any(_is_bound(value, b) for b in bound), (dialect, value, params)
        # Every filter value is its own bound parameter, and nothing else is bound: a
        # value inlined as a literal (e.g. TRUE, or 1 on SQLite) leaves the count short.
        assert len(params) == sum(len(values) for _, values in conditions), (dialect, params)


def _assert_all_bound(stmt: Any, conditions: list[tuple[dict[str, Any], list[Any]]]) -> None:
    for dialect in ("postgresql", "sqlite"):
        sql, params = compile_sql(stmt, dialect)
        bound = list(params.values())
        for _, values in conditions:
            for value in values:
                assert not _sql_mentions(sql, value), (dialect, value, sql)
                assert any(_is_bound(value, b) for b in bound), (dialect, value, params)
        assert len(params) == sum(len(values) for _, values in conditions), (dialect, params)


@settings(max_examples=200, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(
    metric_conditions=st.lists(
        st.lists(condition(), min_size=1, max_size=3), min_size=1, max_size=3
    ),
    filters=st.lists(condition(), max_size=2),
)
def test_every_metric_where_value_is_bound_never_inlined(
    metric_conditions: list[list[tuple[dict[str, Any], list[Any]]]],
    filters: list[tuple[dict[str, Any], list[Any]]],
) -> None:
    """Conditional metrics, and a ratio over them, bind every value and nothing else."""
    registry = load_registry(FIELDSERVICE_REGISTRY)
    metrics: list[dict[str, Any]] = [
        {"agg": "count", "alias": f"m{i}", "where": [c for c, _ in conds]}
        for i, conds in enumerate(metric_conditions)
    ]
    metrics.append({"agg": "sum", "field": "amount", "alias": "billed"})
    metrics.append({"agg": "ratio", "numerator": "m0", "denominator": "billed", "as_percent": True})
    intent = Intent.model_validate(
        {
            "intent_type": "summary",
            "entity": "invoices",
            "metrics": metrics,
            "filters": [c for c, _ in filters],
        }
    )
    result = validate(intent, registry, now=NOW)
    assert result.plan is not None, result.issues
    _assert_all_bound(
        build(result.plan), [c for conds in metric_conditions for c in conds] + filters
    )


# --- compile shape ---


def test_identifiers_come_from_the_registry_and_are_quoted() -> None:
    from ledgerline.core.registry import EntityDef, FieldDef

    reg = Registry(
        schema_version=1,
        draft=False,
        entities={
            "order_lines": EntityDef(
                table="Order Lines",
                fields={
                    "unit_price": FieldDef(column="Unit.Price", type="number", aggregatable=True)
                },
            )
        },
    )
    intent = Intent.model_validate(
        {
            "intent_type": "summary",
            "entity": "order_lines",
            "metrics": [{"agg": "sum", "field": "unit_price"}],
        }
    )
    plan = validate(intent, reg, now=NOW).plan
    assert plan is not None
    sql, _ = compile_sql(build(plan), "postgresql")
    assert 'sum(t0."Unit.Price")' in sql
    assert 'FROM "Order Lines" AS t0' in sql


def test_unsupported_dialect_is_refused() -> None:
    with pytest.raises(ValueError, match="unsupported dialect"):
        dialect_for("oracle")


def test_grains_refuse_other_dialects() -> None:
    stmt = select(GRAINS["month"](literal(date(2026, 1, 1), Date)))
    with pytest.raises(CompileError, match="not implemented"):
        stmt.compile(dialect=mysql.dialect())


def test_compile_renders_in_lists_as_separate_params(registry: Registry) -> None:
    intent = Intent.model_validate(
        {
            "intent_type": "summary",
            "entity": "work_orders",
            "metrics": [{"agg": "count"}],
            "filters": [{"field": "status", "op": "in", "values": ["open", "scheduled"]}],
        }
    )
    plan = validate(intent, registry, now=NOW).plan
    assert plan is not None
    sql, params = compile_sql(build(plan), "sqlite")
    assert "POSTCOMPILE" not in sql
    assert sorted(v for v in params.values() if isinstance(v, str)) == ["open", "scheduled"]


# --- grains across engines ---

EDGE_DATES = [
    date(2024, 12, 29),  # Sunday; ISO week 2024-W52 starts Monday 2024-12-23
    date(2024, 12, 30),  # Monday; ISO week 2025-W01
    date(2025, 1, 1),  # Wednesday in ISO 2025-W01
    date(2025, 3, 31),  # last day of Q1
    date(2025, 4, 1),  # first day of Q2
    date(2025, 6, 30),
    date(2025, 9, 30),
    date(2025, 12, 31),
    date(2026, 1, 4),  # Sunday; ISO 2026-W01 starts 2025-12-29
    date(2026, 2, 28),
    date(2024, 2, 29),  # leap day
]


def _expected(grain: str, day: date) -> date:
    if grain == "day":
        return day
    if grain == "iso_week":
        return day - timedelta(days=day.weekday())
    if grain == "month":
        return day.replace(day=1)
    if grain == "quarter":
        return date(day.year, 3 * ((day.month - 1) // 3) + 1, 1)
    return date(day.year, 1, 1)


@pytest.mark.parametrize("engine_name", ["postgresql", "sqlite"])
@pytest.mark.parametrize("grain", list(GRAINS))
def test_grains_agree_across_engines_on_edge_dates(
    grain: str, engine_name: str, pg_seeded: Engine, sqlite_ro: Engine
) -> None:
    engine = pg_seeded if engine_name == "postgresql" else sqlite_ro
    for day in EDGE_DATES:
        for value, sa_type in (
            (day, Date()),
            (datetime(day.year, day.month, day.day, 23, 59, 59), DateTime()),
        ):
            stmt = select(GRAINS[grain](literal(value, sa_type)))
            got = run(engine, stmt).rows[0][0]
            assert got == _expected(grain, day), (grain, engine_name, value, got)


def test_boolean_filter_values_are_bound(registry: Registry) -> None:
    intent = Intent.model_validate(
        {
            "intent_type": "summary",
            "entity": "customers",
            "metrics": [{"agg": "count"}],
            "filters": [{"field": "is_active", "op": "eq", "value": True}],
        }
    )
    plan = validate(intent, registry, now=NOW).plan
    assert plan is not None
    for dialect in ("postgresql", "sqlite"):
        sql, params = compile_sql(build(plan), dialect)
        assert list(params.values()) == [True], (dialect, sql, params)
        assert "true" not in sql.lower()
        assert "= 1" not in sql


def test_builder_refuses_duplicate_output_labels(registry: Registry) -> None:
    from dataclasses import replace

    intent = Intent.model_validate(
        {
            "intent_type": "grouped_summary",
            "entity": "work_orders",
            "metrics": [{"agg": "count", "alias": "n"}],
            "group_by": [{"field": "status"}],
        }
    )
    plan = validate(intent, registry, now=NOW).plan
    assert plan is not None
    clash = replace(plan, metrics=(replace(plan.metrics[0], label="status"),))
    with pytest.raises(ValueError, match="duplicate output label"):
        build(clash)


def test_datetime_normalisation_refuses_other_dialects() -> None:
    from ledgerline.core.sqlbuild import AsDatetime

    stmt = select(AsDatetime(literal(date(2026, 1, 1), Date)))
    with pytest.raises(CompileError, match="not implemented"):
        stmt.compile(dialect=mysql.dialect())
