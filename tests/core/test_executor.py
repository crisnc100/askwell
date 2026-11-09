"""Executor: read-only on both engines, timeouts fire on both, the row cap holds, and the
audit log records every execution without data rows."""

from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest
from sqlalchemy import Engine, create_engine, select, text

from ledgerline.config import get_settings
from ledgerline.core.audit import AuditEntry, AuditLog, ask_log, params_hash
from ledgerline.core.executor import (
    ExecutionError,
    Executor,
    QueryTimeoutError,
    readonly_engine,
    run,
)
from ledgerline.core.intent import Intent
from ledgerline.core.registry import Registry
from ledgerline.core.validate import QueryPlan, validate
from ledgerline.fieldservice.seed import content_hash
from tests.core.conftest import NOW

WRITES = [
    "INSERT INTO parts (id, sku, name, category, unit_cost, unit_price) "
    "VALUES (9999, 'X', 'x', 'hvac', 1, 1)",
    "UPDATE invoices SET amount = 0",
    "DELETE FROM work_orders",
    "DROP TABLE customers",
    "CREATE TABLE probe (x int)",
]

SLOW = {
    "postgresql": "SELECT pg_sleep(5)",
    "sqlite": "WITH RECURSIVE c(x) AS (SELECT 1 UNION ALL SELECT x + 1 FROM c) "
    "SELECT count(*) FROM c",
}


@pytest.fixture(params=["postgresql", "sqlite"])
def engine(request: pytest.FixtureRequest, pg_seeded: Engine, sqlite_ro: Engine) -> Engine:
    return pg_seeded if request.param == "postgresql" else sqlite_ro


def _owner_hash(engine: Engine, pg_owner: Engine, sqlite_fieldservice: Engine) -> str:
    return content_hash(pg_owner if engine.dialect.name == "postgresql" else sqlite_fieldservice)


@pytest.mark.parametrize("statement", WRITES)
def test_writes_fail(
    engine: Engine, statement: str, pg_owner: Engine, sqlite_fieldservice: Engine
) -> None:
    before = _owner_hash(engine, pg_owner, sqlite_fieldservice)
    with pytest.raises(ExecutionError, match=r"(?i)read-only|readonly|permission denied"):
        run(engine, text(statement))
    assert _owner_hash(engine, pg_owner, sqlite_fieldservice) == before


def test_readonly_postgres_engine_refuses_writes_even_as_owner(pg_owner: Engine) -> None:
    """The executor's own guard, not the role: an owner URL through readonly_engine."""
    engine = readonly_engine(get_settings().database_url)
    try:
        with pytest.raises(ExecutionError, match="read-only"):
            run(engine, text("UPDATE parts SET unit_price = 0"))
        # The session default holds outside run() too.
        with engine.connect() as conn, pytest.raises(Exception, match="read-only"):
            conn.execute(text("DELETE FROM parts"))
    finally:
        engine.dispose()


def test_timeout_fires(engine: Engine) -> None:
    with pytest.raises(QueryTimeoutError):
        run(engine, text(SLOW[engine.dialect.name]), timeout_s=0.3)


def test_the_connection_is_usable_after_a_timeout(engine: Engine) -> None:
    with pytest.raises(QueryTimeoutError):
        run(engine, text(SLOW[engine.dialect.name]), timeout_s=0.2)
    assert run(engine, text("SELECT 1")).rows == [(1,)]


def test_row_cap_truncates(engine: Engine) -> None:
    result = run(engine, text("SELECT id FROM work_orders ORDER BY id"), row_cap=25)
    assert result.row_count == 25
    assert result.truncated
    assert result.columns == ["id"]
    exact = run(engine, text("SELECT id FROM technicians"), row_cap=40)
    assert exact.row_count == 40
    assert not exact.truncated


def test_hidden_columns_are_denied_by_the_database_too(pg_seeded: Engine) -> None:
    for column in ("password_hash", "email"):
        with pytest.raises(ExecutionError, match="permission denied"):
            run(pg_seeded, text(f"SELECT {column} FROM users"))
    with pytest.raises(ExecutionError, match="permission denied"):
        run(pg_seeded, text("SELECT * FROM users"))
    assert run(pg_seeded, text("SELECT username, role FROM users")).row_count == 25


def test_other_errors_are_execution_errors(engine: Engine) -> None:
    with pytest.raises(ExecutionError) as info:
        run(engine, text("SELECT no_such_column FROM parts"))
    assert not isinstance(info.value, QueryTimeoutError)


def test_readonly_engine_rejects_bad_urls(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="file path"):
        readonly_engine("sqlite://")
    with pytest.raises(ValueError, match="no SQLite file"):
        readonly_engine(f"sqlite:///{tmp_path / 'missing.sqlite'}")
    with pytest.raises(ValueError, match="unsupported"):
        readonly_engine("mysql://u@localhost/db")


# --- audit ---


def _plan(registry: Registry) -> QueryPlan:
    intent = Intent.model_validate(
        {
            "intent_type": "row_list",
            "entity": "customers",
            "select": ["name", "region"],
            "filters": [{"field": "segment", "op": "eq", "value": "industrial"}],
            "limit": 5,
        }
    )
    plan = validate(intent, registry, now=NOW).plan
    assert plan is not None
    return plan


def test_execution_is_audited_without_data_rows(
    registry: Registry, sqlite_ro: Engine, tmp_path: Path
) -> None:
    app = create_engine(f"sqlite:///{tmp_path / 'app.sqlite'}")
    executor = Executor(sqlite_ro, audit=AuditLog(app))
    execution = executor.execute(
        _plan(registry),
        question="Which industrial customers do we have?",
        intent_json='{"intent_type": "row_list"}',
        validation_json='{"ok": true}',
        schema_id="fieldservice",
        cost_usd=0.0012,
        model="test/model",
        trace_id="trace-1",
    )
    assert execution.result.row_count == 5
    with app.connect() as conn:
        rows = conn.execute(select(ask_log)).mappings().all()
    assert len(rows) == 1
    row = rows[0]
    assert row["trace_id"] == "trace-1"
    assert row["outcome"] == "answered"
    assert row["row_count"] == 5
    assert row["sql"] == execution.sql
    assert row["params_hash"] == params_hash(execution.params)
    assert row["model"] == "test/model"
    assert row["cost_usd"] == pytest.approx(0.0012)
    stored = json.dumps(dict(row), default=str)
    for data_row in execution.result.rows:
        for value in data_row:
            assert str(value) not in stored
    assert "industrial" not in (row["sql"] or "")


def test_failed_execution_is_audited_as_error(registry: Registry, tmp_path: Path) -> None:
    app = create_engine(f"sqlite:///{tmp_path / 'app.sqlite'}")
    empty = create_engine(f"sqlite:///{tmp_path / 'empty.sqlite'}")
    with empty.begin() as conn:
        conn.execute(text("CREATE TABLE unrelated (x int)"))
    executor = Executor(readonly_engine(str(empty.url)), audit=AuditLog(app))
    with pytest.raises(ExecutionError):
        executor.execute(_plan(registry), question="q")
    with app.connect() as conn:
        row = conn.execute(select(ask_log)).mappings().one()
    assert row["outcome"] == "error"
    assert row["row_count"] is None
    assert row["trace_id"]


def test_execution_without_audit(registry: Registry, sqlite_ro: Engine) -> None:
    execution = Executor(sqlite_ro, row_cap=2).execute(_plan(registry))
    assert execution.result.row_count == 2
    assert execution.result.truncated


def test_audit_writes_to_the_postgres_app_db() -> None:
    url = get_settings().app_database_url
    engine = create_engine(url)
    try:
        log = AuditLog(engine)
        entry = AuditEntry(
            trace_id=str(uuid.uuid4()),
            schema_id="fieldservice",
            question="q",
            intent="{}",
            validation="{}",
            sql=None,
            params_hash=None,
            row_count=None,
            cost_usd=None,
            model=None,
            outcome="refused",
        )
        log.record(entry)
        with engine.connect() as conn:
            found = conn.execute(
                select(ask_log.c.outcome).where(ask_log.c.trace_id == entry.trace_id)
            ).scalar_one()
        assert found == "refused"
    finally:
        engine.dispose()


def test_readonly_role_cannot_reach_the_app_db() -> None:
    ro = get_settings().database_ro_url.rsplit("/", 1)[0] + "/ledgerline_app"
    engine = create_engine(ro)
    try:
        with pytest.raises(Exception, match="CONNECT"), engine.connect():
            pass
    finally:
        engine.dispose()
