"""infra/postgres/roles.sql is idempotent AND keeps the hidden users columns denied."""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ProgrammingError

from ledgerline.config import get_settings
from ledgerline.fieldservice.schema import RO_DENIED_COLUMNS

ROLES_SQL = Path(__file__).resolve().parent.parent / "infra" / "postgres" / "roles.sql"


def _run_roles_sql() -> None:
    psql = shutil.which("psql")
    if psql is None:
        pytest.fail("psql is required to run infra/postgres/roles.sql (tests never skip)")
    url = make_url(get_settings().database_url).set(drivername="postgresql")
    ro_password = make_url(get_settings().database_ro_url).password or ""
    subprocess.run(
        [
            psql,
            url.render_as_string(hide_password=False),
            "-q",
            "-v",
            "ON_ERROR_STOP=1",
            "-v",
            f"ro_password={ro_password}",
            "-f",
            str(ROLES_SQL),
        ],
        check=True,
        capture_output=True,
    )


def test_rerunning_roles_sql_keeps_hidden_columns_denied(pg_seeded: Engine) -> None:
    _run_roles_sql()
    _run_roles_sql()
    for column in sorted(RO_DENIED_COLUMNS["users"]):
        with (
            pg_seeded.connect() as conn,
            pytest.raises(ProgrammingError, match="permission denied"),
        ):
            conn.execute(text(f"SELECT {column} FROM users"))
    with pg_seeded.connect() as conn:
        assert conn.execute(text("SELECT count(username) FROM users")).scalar_one() == 25


def test_roles_sql_denies_the_same_columns_as_the_seed() -> None:
    sql = ROLES_SQL.read_text()
    match = re.search(r"column_name NOT IN \(([^)]*)\)", sql)
    assert match is not None
    denied = {c.strip().strip("'") for c in match.group(1).split(",")}
    assert denied == set(RO_DENIED_COLUMNS["users"])
