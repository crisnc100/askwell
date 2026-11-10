"""The executor: runs a built query read-only, with a timeout and a row cap.

- Postgres: every connection defaults to read-only, and every query runs inside a
  transaction that starts `SET TRANSACTION READ ONLY` and `SET LOCAL statement_timeout`.
- SQLite: the file opens with `mode=ro` (plus `PRAGMA query_only`), and a progress
  handler interrupts a query that passes its deadline.
- Rows past the cap are never fetched (Postgres streams through a server-side cursor);
  the result says it was truncated.
- With an audit log, every execution is recorded (trace id, question, intent,
  validation, SQL, params hash, row count, cost, model). Data rows are never logged.
"""

from __future__ import annotations

import sqlite3
import time
import uuid
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any
from urllib.parse import quote

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError
from sqlalchemy.pool import NullPool
from sqlalchemy.sql import Executable, Select, TextClause

from ledgerline.core.audit import AuditEntry, AuditSink, params_hash
from ledgerline.core.sqlbuild import build, compile_sql
from ledgerline.core.validate import QueryPlan

DEFAULT_TIMEOUT_S = 5.0
DEFAULT_ROW_CAP = 1000


class ExecutionError(Exception):
    """The database refused or failed the query."""


class QueryTimeoutError(ExecutionError):
    """The query ran past its timeout and was cancelled."""


@dataclass(frozen=True)
class QueryResult:
    columns: list[str]
    rows: list[tuple[Any, ...]]
    truncated: bool

    @property
    def row_count(self) -> int:
        return len(self.rows)


@dataclass(frozen=True)
class Execution:
    trace_id: str
    sql: str
    params: dict[str, Any]
    result: QueryResult


def readonly_engine(url: str) -> Engine:
    """An engine that cannot write: SQLite opened `mode=ro`, Postgres read-only by default."""
    parsed = make_url(url)
    backend = parsed.get_backend_name()
    if backend == "sqlite":
        database = parsed.database
        if not database or database == ":memory:":
            raise ValueError("SQLite needs a file path to open read-only")
        path = Path(database).resolve()
        if not path.exists():
            raise ValueError(f"no SQLite file at {path}")
        uri = f"file:{quote(str(path))}?mode=ro"

        def connect() -> sqlite3.Connection:
            conn = sqlite3.connect(uri, uri=True, check_same_thread=False)
            conn.execute("PRAGMA query_only = ON")
            return conn

        return create_engine("sqlite://", creator=connect, poolclass=NullPool)
    if backend == "postgresql":
        engine = create_engine(url, pool_pre_ping=True)

        @event.listens_for(engine, "connect")
        def _readonly_default(dbapi_connection: Any, _record: Any) -> None:  # pyright: ignore[reportUnusedFunction]
            with dbapi_connection.cursor() as cursor:
                cursor.execute("SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY")
            dbapi_connection.commit()

        return engine
    raise ValueError(f"unsupported database backend {backend!r}")


def run(
    engine: Engine,
    stmt: Executable,
    *,
    timeout_s: float = DEFAULT_TIMEOUT_S,
    row_cap: int = DEFAULT_ROW_CAP,
    untrusted: bool = False,
) -> QueryResult:
    """Run one statement in a read-only transaction, then roll back.

    `untrusted=True` is for SQL Ledgerline did not build (a baseline model's query). The
    database driver then guarantees it is a single statement, so a batch such as
    "ROLLBACK; BEGIN READ WRITE; ..." can never end the read-only transaction: on
    Postgres it always runs through a server-side cursor, which uses the extended query
    protocol and refuses more than one command; SQLite's execute runs only one statement
    and refuses the rest."""
    dialect = engine.dialect.name
    try:
        connection = engine.connect()
    except DBAPIError as exc:
        # Connecting is part of executing: a down or refusing database is an
        # ExecutionError, so callers (and the audit log) handle it like any failure.
        raise ExecutionError(f"could not connect to the database: {exc.orig}") from exc
    with connection as conn:
        raw: Any = conn.connection.dbapi_connection
        try:
            if dialect == "postgresql":
                conn.exec_driver_sql("SET TRANSACTION READ ONLY")
                conn.exec_driver_sql(f"SET LOCAL statement_timeout = {int(timeout_s * 1000)}")
            elif dialect == "sqlite":
                deadline = time.monotonic() + timeout_s
                raw.set_progress_handler(lambda: int(time.monotonic() > deadline), 1000)
            # A server-side cursor on Postgres: rows arrive in batches as they are fetched,
            # so at most row_cap + 1 rows ever reach this process. (SQLite's cursor is
            # already incremental.)
            stream = untrusted or _is_query(stmt)
            options = {"stream_results": True, "max_row_buffer": row_cap + 1} if stream else {}
            result = conn.execute(stmt, execution_options=options)
            if not result.returns_rows:
                # e.g. a comment-only statement: nothing ran, and there is nothing to read.
                raise ExecutionError("the statement returned no result set")
            columns = list(result.keys())
            rows = [tuple(row) for row in result.fetchmany(row_cap + 1)]
        except DBAPIError as exc:
            if _is_timeout(exc):
                raise QueryTimeoutError(f"query cancelled after {timeout_s}s") from exc
            raise ExecutionError(str(exc.orig)) from exc
        finally:
            if dialect == "sqlite":
                raw.set_progress_handler(None, 0)
            conn.rollback()
    return QueryResult(columns, rows[:row_cap], len(rows) > row_cap)


def _is_query(stmt: Executable) -> bool:
    """Only a SELECT can run through a server-side cursor (Postgres wraps it in DECLARE
    CURSOR). Anything else runs plainly, so the read-only transaction is what refuses
    a write, with its own error."""
    if isinstance(stmt, Select):
        return True
    if isinstance(stmt, TextClause):
        return stmt.text.lstrip().lower().startswith(("select", "with"))
    return False


def _is_timeout(exc: DBAPIError) -> bool:
    orig = exc.orig
    if type(orig).__name__ == "QueryCanceled":
        return True
    return isinstance(orig, sqlite3.OperationalError) and "interrupted" in str(orig)


class Executor:
    def __init__(
        self,
        engine: Engine,
        *,
        audit: AuditSink | None = None,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        row_cap: int = DEFAULT_ROW_CAP,
    ) -> None:
        self.engine = engine
        self.audit = audit
        self.timeout_s = timeout_s
        self.row_cap = row_cap

    def execute(
        self,
        plan: QueryPlan,
        *,
        question: str = "",
        intent_json: str = "",
        validation_json: str = "",
        schema_id: str | None = None,
        cost_usd: float | None = None,
        model: str | None = None,
        trace_id: str | None = None,
    ) -> Execution:
        trace = trace_id or str(uuid.uuid4())
        stmt = build(plan)
        sql, params = compile_sql(stmt, self.engine.dialect.name)
        entry = AuditEntry(
            trace_id=trace,
            schema_id=schema_id,
            question=question,
            intent=intent_json,
            validation=validation_json,
            sql=sql,
            params_hash=params_hash(params),
            row_count=None,
            cost_usd=cost_usd,
            model=model,
            outcome="error",
        )
        try:
            result = run(self.engine, stmt, timeout_s=self.timeout_s, row_cap=self.row_cap)
        except ExecutionError:
            if self.audit is not None:
                self.audit.record(entry)
            raise
        if self.audit is not None:
            self.audit.record(replace(entry, row_count=result.row_count, outcome="answered"))
        return Execution(trace, sql, params, result)
