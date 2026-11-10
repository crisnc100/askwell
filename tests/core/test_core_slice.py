"""Fixes for the PR1 core slice review (builds/v01/core-slice-findings.md, f1-f4, x2)."""

from __future__ import annotations

import time
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy import Engine, create_engine, text

from ledgerline.config import get_settings
from ledgerline.core.executor import readonly_engine, run
from ledgerline.core.intent import Intent
from ledgerline.core.registry import EntityDef, FieldDef, Registry
from ledgerline.core.registry_init import init_registry
from ledgerline.core.sqlbuild import build, compile_sql
from ledgerline.core.validate import validate
from tests.core.conftest import NOW


def _plan(registry: Registry, **intent: object):
    result = validate(Intent.model_validate(intent), registry, now=NOW)
    assert result.plan is not None, result.issues
    return result.plan


# --- f1: one canonical form for SQLite DATETIME in comparisons, aggregates, groups, order ---

# Every row is a representation of one of two instants: 09:00 UTC (a) or 10:30 UTC (b).
MIXED = [
    (1, "2026-06-01T09:00:00", "2026-06-01 10:30:00.000000"),
    (2, "2026-06-01 09:00:00.000000", "2026-06-01T12:30:00+02:00"),
    (3, "2026-06-01 09:00:00Z", "2026-06-01 10:30:00"),
    (4, "2026-06-01T11:00:00+02:00", "2026-06-01 10:30:00.000000Z"),
]


@pytest.fixture
def mixed_datetimes(tmp_path: Path) -> Iterator[tuple[Engine, Registry]]:
    path = tmp_path / "mixed.sqlite"
    writer = create_engine(f"sqlite:///{path}")
    with writer.begin() as conn:
        conn.execute(text("CREATE TABLE ev (id INTEGER PRIMARY KEY, a DATETIME, b DATETIME)"))
        for row in MIXED:
            conn.execute(
                text("INSERT INTO ev VALUES (:i, :a, :b)"), {"i": row[0], "a": row[1], "b": row[2]}
            )
    writer.dispose()
    engine = readonly_engine(f"sqlite:///{path}")
    registry = Registry(
        schema_version=1,
        draft=False,
        entities={
            "ev": EntityDef(
                table="ev",
                fields={
                    "id": FieldDef(column="id", type="integer"),
                    "a": FieldDef(column="a", type="datetime", aggregatable=True),
                    "b": FieldDef(column="b", type="datetime", aggregatable=True),
                },
            )
        },
    )
    yield engine, registry
    engine.dispose()


def test_sqlite_datetime_column_comparisons_are_format_independent(
    mixed_datetimes: tuple[Engine, Registry],
) -> None:
    engine, registry = mixed_datetimes
    plan = _plan(
        registry,
        intent_type="row_list",
        entity="ev",
        select=["id"],
        filters=[{"field": "a", "op": "lt", "other_field": "b"}],
        order_by=[{"target": "id"}],
    )
    assert [r[0] for r in run(engine, build(plan)).rows] == [1, 2, 3, 4]


def test_sqlite_datetime_max_group_and_order_are_format_independent(
    mixed_datetimes: tuple[Engine, Registry],
) -> None:
    engine, registry = mixed_datetimes
    top = _plan(
        registry,
        intent_type="summary",
        entity="ev",
        metrics=[{"agg": "max", "field": "a"}, {"agg": "count_distinct", "field": "b"}],
    )
    assert run(engine, build(top)).rows == [(datetime(2026, 6, 1, 9, 0), 1)]
    groups = _plan(
        registry,
        intent_type="grouped_summary",
        entity="ev",
        metrics=[{"agg": "count"}],
        group_by=[{"field": "b"}],
    )
    assert run(engine, build(groups)).rows == [(datetime(2026, 6, 1, 10, 30), 4)]
    ordered = _plan(
        registry,
        intent_type="row_list",
        entity="ev",
        select=["id"],
        order_by=[{"target": "a", "direction": "desc"}, {"target": "id"}],
    )
    assert [r[0] for r in run(engine, build(ordered)).rows] == [1, 2, 3, 4]


# --- f2: fractional HAVING thresholds are not cast to the aggregate's integer type ---


@pytest.mark.parametrize("engine_name", ["postgresql", "sqlite"])
def test_fractional_having_threshold_keeps_groups_of_two(
    engine_name: str, registry: Registry, pg_seeded: Engine, sqlite_ro: Engine
) -> None:
    engine = pg_seeded if engine_name == "postgresql" else sqlite_ro
    plan = _plan(
        registry,
        intent_type="grouped_summary",
        entity="invoices",
        metrics=[{"agg": "count", "alias": "n"}],
        group_by=[{"field": "work_order_id"}],
        having=[{"metric": "n", "op": "gt", "value": 1.5}],
    )
    with pg_seeded.connect() as conn:
        expected = conn.execute(
            text(
                "SELECT count(*) FROM (SELECT work_order_id FROM invoices GROUP BY 1 "
                "HAVING count(*) = 2) x"
            )
        ).scalar_one()
    assert expected > 0
    assert len(run(engine, build(plan), row_cap=10_000).rows) == expected
    sql, _ = compile_sql(build(plan), "postgresql")
    assert "::INTEGER" not in sql.split("HAVING")[1]


# --- f3: declared foreign keys resolve by schema and exact name ---

FK_SCHEMA_A, FK_SCHEMA_B = "ledgerline_test_fk_a", "ledgerline_test_fk_b"


@pytest.fixture
def fk_schemas(pg_owner: Engine) -> Iterator[Engine]:
    with pg_owner.begin() as conn:
        for schema in (FK_SCHEMA_A, FK_SCHEMA_B):
            conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
            conn.execute(text(f"CREATE SCHEMA {schema}"))
        conn.execute(text(f"CREATE TABLE {FK_SCHEMA_A}.customers (id int PRIMARY KEY)"))
        conn.execute(text(f'CREATE TABLE {FK_SCHEMA_A}."Customers" (id int PRIMARY KEY)'))
        conn.execute(text(f"CREATE TABLE {FK_SCHEMA_B}.customers (id int PRIMARY KEY)"))
        conn.execute(
            text(
                f"CREATE TABLE {FK_SCHEMA_A}.orders (id int PRIMARY KEY, "
                f"archived_customer int REFERENCES {FK_SCHEMA_B}.customers(id), "
                f'quoted_customer int REFERENCES {FK_SCHEMA_A}."Customers"(id))'
            )
        )
    url = get_settings().database_url
    engine = create_engine(url, connect_args={"options": f"-c search_path={FK_SCHEMA_A}"})
    yield engine
    engine.dispose()
    with pg_owner.begin() as conn:
        for schema in (FK_SCHEMA_A, FK_SCHEMA_B):
            conn.execute(text(f"DROP SCHEMA {schema} CASCADE"))


def test_declared_keys_resolve_by_schema_and_exact_name(fk_schemas: Engine) -> None:
    result = init_registry(fk_schemas)
    registry = result.registry
    by_field = {r.from_field: r for r in registry.relationships if r.from_entity == "orders"}
    # The other-schema target is not introspected: skipped with a warning, never redirected.
    assert "archived_customer" not in by_field
    assert any("archived_customer" in w for w in result.warnings)
    # The quoted "Customers" target is that table, not lowercase customers.
    quoted = by_field["quoted_customer"]
    assert registry.entities[quoted.to_entity].table == "Customers"


# --- f4: Postgres never buffers more than the row cap ---


def test_postgres_row_cap_does_not_fetch_the_whole_result(pg_seeded: Engine) -> None:
    # About 1.8e11 rows. Buffering them client-side cannot finish inside the 2 s timeout;
    # a server-side cursor returns the first rows at once.
    huge = text(
        "SELECT w.id FROM work_orders w CROSS JOIN work_order_parts p CROSS JOIN invoices i"
    )
    started = time.monotonic()
    result = run(pg_seeded, huge, row_cap=5, timeout_s=2.0)
    assert result.row_count == 5
    assert result.truncated
    assert time.monotonic() - started < 2.0


# --- x2: ORDER BY on a field reached only through any_of keeps the join optional ---


@pytest.mark.parametrize("engine_name", ["postgresql", "sqlite"])
def test_order_by_does_not_force_an_inner_join(
    engine_name: str, registry: Registry, pg_seeded: Engine, sqlite_ro: Engine
) -> None:
    engine = pg_seeded if engine_name == "postgresql" else sqlite_ro
    plan = _plan(
        registry,
        intent_type="row_list",
        entity="work_orders",
        select=["id"],
        filters=[
            {
                "any_of": [
                    {"field": "priority", "op": "eq", "value": "urgent"},
                    {"field": "technicians.skill_level", "op": "eq", "value": "senior"},
                ]
            }
        ],
        order_by=[{"target": "technicians.full_name"}, {"target": "id"}],
    )
    with pg_seeded.connect() as conn:
        expected = conn.execute(
            text(
                "SELECT count(*) FROM work_orders w LEFT JOIN technicians t "
                "ON t.id = w.technician_id WHERE w.priority = 'urgent' OR t.skill_level = 'senior'"
            )
        ).scalar_one()
    assert run(engine, build(plan), row_cap=10_000).row_count == expected


def test_unparseable_datetime_text_is_kept_not_turned_into_null(tmp_path: Path) -> None:
    """strftime returns NULL for text it cannot read; the canonical form falls back to the
    stored text, so such values still count, group and compare as themselves."""
    path = tmp_path / "odd.sqlite"
    writer = create_engine(f"sqlite:///{path}")
    with writer.begin() as conn:
        conn.execute(text("CREATE TABLE ev (id INTEGER PRIMARY KEY, at DATETIME)"))
        conn.execute(
            text(
                "INSERT INTO ev VALUES (1, 'not a time'), (2, 'also not a time'), "
                "(3, '2026-06-01 10:30:00'), (4, 'not a time')"
            )
        )
    writer.dispose()
    engine = readonly_engine(f"sqlite:///{path}")
    registry = Registry(
        schema_version=1,
        draft=False,
        entities={
            "ev": EntityDef(
                table="ev",
                fields={
                    "id": FieldDef(column="id", type="integer"),
                    "at": FieldDef(column="at", type="datetime"),
                },
            )
        },
    )
    try:
        distinct = _plan(
            registry,
            intent_type="summary",
            entity="ev",
            metrics=[{"agg": "count_distinct", "field": "at"}],
        )
        assert run(engine, build(distinct)).rows == [(3,)]
        groups = _plan(
            registry,
            intent_type="grouped_summary",
            entity="ev",
            metrics=[{"agg": "count"}],
            group_by=[{"field": "at"}],
        )
        counts = sorted(r[1] for r in run(engine, build(groups)).rows)
        assert counts == [1, 1, 2]
        same = _plan(
            registry,
            intent_type="summary",
            entity="ev",
            metrics=[{"agg": "count"}],
            filters=[{"field": "at", "op": "eq", "other_field": "at"}],
        )
        assert run(engine, build(same)).rows == [(4,)]
    finally:
        engine.dispose()
