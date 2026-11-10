"""The `ask_log` audit table in the app DB.

It never stores result rows, and never the bound parameter values (the filter values a
query ran with): only a SHA-256 of them, which proves which values ran without keeping
them."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from sqlalchemy import (
    Column,
    DateTime,
    Engine,
    Float,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    insert,
)

metadata = MetaData()

ask_log = Table(
    "ask_log",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("trace_id", String(36), nullable=False, unique=True),
    Column("created_at", DateTime, nullable=False),
    Column("schema_id", String(120), nullable=True),
    Column("question", Text, nullable=False),
    Column("intent", Text, nullable=False),  # the intent JSON
    Column("validation", Text, nullable=False),  # the validation outcome JSON
    Column("sql", Text, nullable=True),  # placeholders only, never values
    Column("params_hash", String(64), nullable=True),
    Column("row_count", Integer, nullable=True),
    Column("cost_usd", Float, nullable=True),
    Column("model", String(200), nullable=True),
    Column("outcome", String(20), nullable=False),  # answered | refused | error
)

Outcome = Literal["answered", "refused", "error"]


def params_hash(params: dict[str, Any]) -> str:
    """SHA-256 of the bound parameters, so the audit proves which values ran without
    storing them."""
    canonical = json.dumps(params, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


@dataclass(frozen=True)
class AuditEntry:
    trace_id: str
    schema_id: str | None
    question: str
    intent: str
    validation: str
    sql: str | None
    params_hash: str | None
    row_count: int | None
    cost_usd: float | None
    model: str | None
    outcome: Outcome


class AuditLog:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine
        metadata.create_all(engine, tables=[ask_log])

    def record(self, entry: AuditEntry) -> None:
        now = datetime.now(UTC).replace(tzinfo=None)
        values: dict[str, Any] = {**entry.__dict__, "created_at": now}
        with self.engine.begin() as conn:
            conn.execute(insert(ask_log).values(**values))
