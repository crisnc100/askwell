from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.exc import OperationalError

from askwell.config import get_settings
from askwell.fieldservice.seed import Dataset, content_hash, generate, load

pytest_plugins = ["pytester", "tests.plugins.zero_skips"]

NOT_SEEDED = (
    "Postgres is not reachable or not seeded. Run `docker compose up -d db` and "
    "`uv run askwell seed`. (Tests never skip: a missing DB is a failure.)"
)


@pytest.fixture(scope="session")
def dataset() -> Dataset:
    return generate(get_settings().now)


@pytest.fixture(scope="session")
def sqlite_fieldservice(tmp_path_factory: pytest.TempPathFactory, dataset: Dataset) -> Engine:
    path: Path = tmp_path_factory.mktemp("fieldservice") / "fieldservice.sqlite"
    engine = create_engine(f"sqlite:///{path}")
    load(engine, dataset)
    return engine


def _connect_or_fail(url: str) -> Engine:
    engine = create_engine(url)
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except OperationalError as exc:
        pytest.fail(f"{NOT_SEEDED}\n{exc}")
    return engine


@pytest.fixture(scope="session")
def pg_ro() -> Iterator[Engine]:
    """The seeded fieldservice Postgres, as the read-only role."""
    engine = _connect_or_fail(get_settings().database_ro_url)
    yield engine
    engine.dispose()


@pytest.fixture(scope="session")
def pg_owner() -> Iterator[Engine]:
    """The fieldservice Postgres as the owner role (reads every column, for content checks)."""
    engine = _connect_or_fail(get_settings().database_url)
    yield engine
    engine.dispose()


@pytest.fixture(scope="session")
def pg_seeded(pg_ro: Engine, pg_owner: Engine, sqlite_fieldservice: Engine) -> Engine:
    """`pg_ro`, after checking the database holds exactly the current seed data.

    The content hash is read as the owner: the read-only role is denied
    users.email and users.password_hash, so it cannot read every column."""
    expected = content_hash(sqlite_fieldservice)
    actual = content_hash(pg_owner)
    if actual != expected:
        pytest.fail(f"{NOT_SEEDED}\nPostgres content {actual} != expected seed {expected}")
    return pg_ro
