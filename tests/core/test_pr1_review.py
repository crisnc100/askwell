"""Fixes for the PR1 full review (builds/v01/pr1-review-findings.md, f2-f8)."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import Engine, create_engine, text

from ledgerline.config import get_settings
from ledgerline.core.audit import AuditLog, ask_log
from ledgerline.core.executor import ExecutionError, Executor, readonly_engine, run
from ledgerline.core.intent import Intent
from ledgerline.core.registry import Registry
from ledgerline.core.registry_init import init_registry
from ledgerline.core.sqlbuild import build
from ledgerline.core.validate import validate
from tests.core.conftest import NOW


def _plan(registry: Registry, **intent: object):
    result = validate(Intent.model_validate(intent), registry, now=NOW)
    assert result.plan is not None, result.issues
    return result.plan


# --- f2: OR across an optional join keeps base rows that have no joined row ---


@pytest.mark.parametrize("engine_name", ["postgresql", "sqlite"])
def test_or_across_a_nullable_join_keeps_unjoined_rows(
    engine_name: str, registry: Registry, pg_seeded: Engine, sqlite_ro: Engine
) -> None:
    engine = pg_seeded if engine_name == "postgresql" else sqlite_ro
    plan = _plan(
        registry,
        intent_type="summary",
        entity="work_orders",
        metrics=[{"agg": "count"}],
        filters=[
            {
                "any_of": [
                    {"field": "priority", "op": "eq", "value": "urgent"},
                    {"field": "technicians.skill_level", "op": "eq", "value": "senior"},
                ]
            }
        ],
    )
    with pg_seeded.connect() as conn:
        expected = conn.execute(
            text(
                "SELECT count(*) FROM work_orders w "
                "LEFT JOIN technicians t ON t.id = w.technician_id "
                "WHERE w.priority = 'urgent' OR t.skill_level = 'senior'"
            )
        ).scalar_one()
    assert run(engine, build(plan)).rows == [(expected,)]


@pytest.mark.parametrize("engine_name", ["postgresql", "sqlite"])
def test_and_filters_and_groups_still_use_inner_joins(
    engine_name: str, registry: Registry, pg_seeded: Engine, sqlite_ro: Engine
) -> None:
    """Grouping by a joined field keeps inner-join semantics (no NULL group)."""
    engine = pg_seeded if engine_name == "postgresql" else sqlite_ro
    plan = _plan(
        registry,
        intent_type="grouped_summary",
        entity="work_orders",
        metrics=[{"agg": "count"}],
        group_by=[{"field": "technicians.skill_level"}],
    )
    rows = run(engine, build(plan)).rows
    assert all(row[0] is not None for row in rows)


# --- f3: SQLite datetime filters do not depend on the stored text format ---


@pytest.fixture
def mixed_format_sqlite(tmp_path: Path) -> Iterator[tuple[Engine, Registry]]:
    path = tmp_path / "events.sqlite"
    writer = create_engine(f"sqlite:///{path}")
    with writer.begin() as conn:
        conn.execute(text("CREATE TABLE events (id INTEGER PRIMARY KEY, at DATETIME)"))
        conn.execute(
            text(
                "INSERT INTO events VALUES (1, '2026-06-01 10:30:00'), "
                "(2, '2026-06-01 10:30:00.000000'), (3, '2026-06-01T10:30:00'), "
                "(4, '2026-06-01 10:29:59.999999'), (5, '2026-06-01 10:30:00.000001')"
            )
        )
    writer.dispose()
    engine = readonly_engine(f"sqlite:///{path}")
    registry = init_registry(engine).registry.model_copy(update={"draft": False})
    yield engine, registry
    engine.dispose()


@pytest.mark.parametrize(
    ("op", "ids"),
    [("eq", [1, 2, 3]), ("lt", [4]), ("lte", [1, 2, 3, 4]), ("gt", [5]), ("gte", [1, 2, 3, 5])],
)
def test_sqlite_datetime_filters_ignore_the_stored_text_format(
    mixed_format_sqlite: tuple[Engine, Registry], op: str, ids: list[int]
) -> None:
    engine, registry = mixed_format_sqlite
    plan = _plan(
        registry,
        intent_type="row_list",
        entity="events",
        select=["id"],
        filters=[{"field": "at", "op": op, "value": "2026-06-01T10:30:00"}],
        order_by=[{"target": "id"}],
    )
    assert [r[0] for r in run(engine, build(plan)).rows] == ids


# --- f4: 64-bit integers are not narrowed to 32 bits on Postgres ---

BIG_SCHEMA = "ledgerline_test_bigint"


@pytest.fixture
def bigint_pg(pg_owner: Engine) -> Iterator[Engine]:
    with pg_owner.begin() as conn:
        conn.execute(text(f"DROP SCHEMA IF EXISTS {BIG_SCHEMA} CASCADE"))
        conn.execute(text(f"CREATE SCHEMA {BIG_SCHEMA}"))
        conn.execute(text(f"CREATE TABLE {BIG_SCHEMA}.big (id bigint PRIMARY KEY, n int)"))
        conn.execute(text(f"INSERT INTO {BIG_SCHEMA}.big VALUES (7000000001, 1), (2, 2)"))
        conn.execute(text(f"GRANT USAGE ON SCHEMA {BIG_SCHEMA} TO ledgerline_ro"))
        conn.execute(text(f"GRANT SELECT ON {BIG_SCHEMA}.big TO ledgerline_ro"))
    engine = readonly_engine(get_settings().database_ro_url)
    yield engine
    engine.dispose()
    with pg_owner.begin() as conn:
        conn.execute(text(f"DROP SCHEMA {BIG_SCHEMA} CASCADE"))


def test_bigint_values_beyond_32_bits_filter_correctly(bigint_pg: Engine) -> None:
    from ledgerline.core.registry import EntityDef, FieldDef

    registry = Registry(
        schema_version=1,
        draft=False,
        entities={
            "big": EntityDef(
                table="big",
                db_schema=BIG_SCHEMA,
                fields={
                    "id": FieldDef(column="id", type="integer"),
                    "n": FieldDef(column="n", type="integer"),
                },
            )
        },
    )
    plan = _plan(
        registry,
        intent_type="row_list",
        entity="big",
        select=["n"],
        filters=[{"field": "id", "op": "eq", "value": 7000000001}],
    )
    assert run(bigint_pg, build(plan)).rows == [(1,)]
    plan = _plan(
        registry,
        intent_type="row_list",
        entity="big",
        select=["n"],
        filters=[{"field": "id", "op": "in", "values": [7000000001, 2]}],
        order_by=[{"target": "n"}],
    )
    assert run(bigint_pg, build(plan)).rows == [(1,), (2,)]


# --- f5: no inference on a column whose declared foreign key was skipped ---


def test_no_inferred_relationship_on_a_skipped_declared_key(tmp_path: Path) -> None:
    path = tmp_path / "fk.sqlite"
    writer = create_engine(f"sqlite:///{path}")
    with writer.begin() as conn:
        conn.execute(text("CREATE TABLE countries (id INTEGER PRIMARY KEY, code TEXT UNIQUE)"))
        conn.execute(text("CREATE TABLE codes (id INTEGER PRIMARY KEY, label TEXT)"))
        conn.execute(
            text(
                "CREATE TABLE addresses (id INTEGER PRIMARY KEY, "
                "code_id TEXT REFERENCES countries(code))"
            )
        )
    writer.dispose()
    engine = readonly_engine(f"sqlite:///{path}")
    try:
        result = init_registry(engine)
    finally:
        engine.dispose()
    assert not [r for r in result.registry.relationships if r.from_entity == "addresses"]
    assert any("addresses.code_id" in w for w in result.warnings)


# --- f7: a connection failure is an ExecutionError, and it is audited ---


def test_connection_failure_is_an_execution_error_and_audited(
    registry: Registry, tmp_path: Path
) -> None:
    dead = readonly_engine("postgresql+psycopg://nobody:nothing@127.0.0.1:1/none")
    plan = _plan(registry, intent_type="summary", entity="parts", metrics=[{"agg": "count"}])
    with pytest.raises(ExecutionError):
        run(dead, build(plan))
    app = create_engine(f"sqlite:///{tmp_path / 'app.sqlite'}")
    with pytest.raises(ExecutionError):
        Executor(dead, audit=AuditLog(app)).execute(plan, question="q")
    with app.connect() as conn:
        outcomes = [
            r[0] for r in conn.execute(ask_log.select().with_only_columns(ask_log.c.outcome))
        ]
    assert outcomes == ["error"]
    dead.dispose()
