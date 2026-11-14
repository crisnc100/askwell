"""One small synthetic database on both engines: the same statements run in a fresh
SQLite file and in a fresh Postgres schema, and each comes back opened read-only the way
the executor opens it."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import Engine, create_engine, make_url, text

from askwell.config import get_settings
from askwell.core.executor import readonly_engine


@contextmanager
def sqlite_db(path: Path, statements: list[str]) -> Iterator[Engine]:
    writer = create_engine(f"sqlite:///{path}")
    with writer.begin() as conn:
        for statement in statements:
            conn.execute(text(statement))
    writer.dispose()
    engine = readonly_engine(f"sqlite:///{path}")
    try:
        yield engine
    finally:
        engine.dispose()


@contextmanager
def pg_db(pg_owner: Engine, schema: str, statements: list[str]) -> Iterator[Engine]:
    """Tables in their own schema, readable by the read-only role. The returned engine's
    search path is that schema, so the statements and init_registry need no prefix."""
    with pg_owner.begin() as conn:
        conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        conn.execute(text(f"CREATE SCHEMA {schema}"))
        conn.execute(text(f"SET LOCAL search_path TO {schema}"))
        for statement in statements:
            conn.execute(text(statement))
        conn.execute(text(f"GRANT USAGE ON SCHEMA {schema} TO askwell_ro"))
        conn.execute(text(f"GRANT SELECT ON ALL TABLES IN SCHEMA {schema} TO askwell_ro"))
    url = make_url(get_settings().database_ro_url).update_query_dict(
        {"options": f"-csearch_path={schema}"}
    )
    engine = readonly_engine(url.render_as_string(hide_password=False))
    try:
        yield engine
    finally:
        engine.dispose()
        with pg_owner.begin() as conn:
            conn.execute(text(f"DROP SCHEMA {schema} CASCADE"))
