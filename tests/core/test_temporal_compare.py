"""Column comparisons between a DATE and a DATETIME normalise both sides to a datetime on
both engines, so midnight on the same day compares equal (it did not on SQLite, where the
raw operands compared as strings)."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import Engine, create_engine, text

from ledgerline.config import get_settings
from ledgerline.core.executor import readonly_engine, run
from ledgerline.core.intent import Intent
from ledgerline.core.registry import EntityDef, FieldDef, Registry
from ledgerline.core.sqlbuild import build
from ledgerline.core.validate import validate
from tests.core.conftest import NOW

ROWS = [
    (1, "2026-06-01 00:00:00", "2026-06-01"),  # midnight on the day: equal
    (2, "2026-06-01 10:30:00", "2026-06-01"),  # later that day: greater
    (3, "2026-05-31 23:59:59", "2026-06-01"),  # the evening before: less
    (4, "2026-06-03 00:00:00", "2026-06-02"),  # a day after: greater
]
EXPECTED = {"eq": [1], "neq": [2, 3, 4], "gt": [2, 4], "gte": [1, 2, 4], "lt": [3], "lte": [1, 3]}
SCHEMA = "ledgerline_test_temporal"


def _registry(db_schema: str | None) -> Registry:
    return Registry(
        schema_version=1,
        draft=False,
        entities={
            "jobs": EntityDef(
                table="jobs",
                db_schema=db_schema,
                fields={
                    "id": FieldDef(column="id", type="integer"),
                    "done_at": FieldDef(column="done_at", type="datetime"),
                    "due_on": FieldDef(column="due_on", type="date"),
                },
            )
        },
    )


@pytest.fixture
def sqlite_jobs(tmp_path: Path) -> Iterator[Engine]:
    """SQLite with timestamps stored the way SQLAlchemy writes them (with microseconds)."""
    path = tmp_path / "jobs.sqlite"
    writer = create_engine(f"sqlite:///{path}")
    with writer.begin() as conn:
        conn.execute(
            text("CREATE TABLE jobs (id INTEGER PRIMARY KEY, done_at DATETIME, due_on DATE)")
        )
        for i, done, due in ROWS:
            conn.execute(
                text("INSERT INTO jobs VALUES (:i, :d, :u)"),
                {"i": i, "d": f"{done}.000000", "u": due},
            )
    writer.dispose()
    engine = readonly_engine(f"sqlite:///{path}")
    yield engine
    engine.dispose()


@pytest.fixture
def pg_jobs(pg_owner: Engine) -> Iterator[Engine]:
    with pg_owner.begin() as conn:
        conn.execute(text(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE"))
        conn.execute(text(f"CREATE SCHEMA {SCHEMA}"))
        conn.execute(
            text(f"CREATE TABLE {SCHEMA}.jobs (id int PRIMARY KEY, done_at timestamp, due_on date)")
        )
        for i, done, due in ROWS:
            conn.execute(
                text(
                    f"INSERT INTO {SCHEMA}.jobs "
                    "VALUES (:i, CAST(:d AS timestamp), CAST(:u AS date))"
                ),
                {"i": i, "d": done, "u": due},
            )
        conn.execute(text(f"GRANT USAGE ON SCHEMA {SCHEMA} TO ledgerline_ro"))
        conn.execute(text(f"GRANT SELECT ON {SCHEMA}.jobs TO ledgerline_ro"))
    engine = readonly_engine(get_settings().database_ro_url)
    yield engine
    engine.dispose()
    with pg_owner.begin() as conn:
        conn.execute(text(f"DROP SCHEMA {SCHEMA} CASCADE"))


@pytest.mark.parametrize("engine_name", ["postgresql", "sqlite"])
@pytest.mark.parametrize("op", sorted(EXPECTED))
def test_date_vs_datetime_comparison_including_midnight(
    op: str, engine_name: str, request: pytest.FixtureRequest
) -> None:
    engine: Engine = request.getfixturevalue(
        "pg_jobs" if engine_name == "postgresql" else "sqlite_jobs"
    )
    registry = _registry(SCHEMA if engine_name == "postgresql" else None)
    for left, right, flipped in (("done_at", "due_on", False), ("due_on", "done_at", True)):
        intent = Intent.model_validate(
            {
                "intent_type": "row_list",
                "entity": "jobs",
                "select": ["id"],
                "filters": [{"field": left, "op": op, "other_field": right}],
                "order_by": [{"target": "id"}],
            }
        )
        plan = validate(intent, registry, now=NOW).plan
        assert plan is not None
        got = [row[0] for row in run(engine, build(plan)).rows]
        mirror = {"gt": "lt", "gte": "lte", "lt": "gt", "lte": "gte"}.get(op, op)
        assert got == EXPECTED[mirror if flipped else op], (engine_name, left, op, right)


MICRO_SCHEMA = "ledgerline_test_micro"
MICRO_ROWS = [
    (1, "2026-06-01 00:00:00.000001", "2026-06-01"),  # one microsecond after midnight
    (2, "2026-06-01 00:00:00", "2026-06-01"),  # exactly midnight
    (3, "2026-05-31 23:59:59.999999", "2026-06-01"),  # one microsecond before
]


@pytest.fixture
def micro_engines(tmp_path: Path, pg_owner: Engine) -> Iterator[dict[str, tuple[Engine, Registry]]]:
    path = tmp_path / "micro.sqlite"
    writer = create_engine(f"sqlite:///{path}")
    with writer.begin() as conn:
        conn.execute(
            text("CREATE TABLE jobs (id INTEGER PRIMARY KEY, done_at DATETIME, due_on DATE)")
        )
        for i, done, due in MICRO_ROWS:
            stored = done if "." in done else f"{done}.000000"
            conn.execute(
                text("INSERT INTO jobs VALUES (:i, :d, :u)"), {"i": i, "d": stored, "u": due}
            )
    writer.dispose()
    with pg_owner.begin() as conn:
        conn.execute(text(f"DROP SCHEMA IF EXISTS {MICRO_SCHEMA} CASCADE"))
        conn.execute(text(f"CREATE SCHEMA {MICRO_SCHEMA}"))
        conn.execute(
            text(
                f"CREATE TABLE {MICRO_SCHEMA}.jobs "
                "(id int PRIMARY KEY, done_at timestamp, due_on date)"
            )
        )
        for i, done, due in MICRO_ROWS:
            conn.execute(
                text(
                    f"INSERT INTO {MICRO_SCHEMA}.jobs "
                    "VALUES (:i, CAST(:d AS timestamp), CAST(:u AS date))"
                ),
                {"i": i, "d": done, "u": due},
            )
        conn.execute(text(f"GRANT USAGE ON SCHEMA {MICRO_SCHEMA} TO ledgerline_ro"))
        conn.execute(text(f"GRANT SELECT ON {MICRO_SCHEMA}.jobs TO ledgerline_ro"))
    lite = readonly_engine(f"sqlite:///{path}")
    pg = readonly_engine(get_settings().database_ro_url)
    yield {"sqlite": (lite, _registry(None)), "postgresql": (pg, _registry(MICRO_SCHEMA))}
    lite.dispose()
    pg.dispose()
    with pg_owner.begin() as conn:
        conn.execute(text(f"DROP SCHEMA {MICRO_SCHEMA} CASCADE"))


@pytest.mark.parametrize("engine_name", ["postgresql", "sqlite"])
def test_date_vs_datetime_keeps_microseconds(
    engine_name: str, micro_engines: dict[str, tuple[Engine, Registry]]
) -> None:
    engine, registry = micro_engines[engine_name]
    expected = {"gt": [1], "eq": [2], "lt": [3]}
    for op, ids in expected.items():
        intent = Intent.model_validate(
            {
                "intent_type": "row_list",
                "entity": "jobs",
                "select": ["id"],
                "filters": [{"field": "done_at", "op": op, "other_field": "due_on"}],
                "order_by": [{"target": "id"}],
            }
        )
        plan = validate(intent, registry, now=NOW).plan
        assert plan is not None
        assert [row[0] for row in run(engine, build(plan)).rows] == ids, (engine_name, op)
