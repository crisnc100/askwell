"""The systems under test. Each one answers an item with rows, a refusal or an error.

- ledgerline: the full pipeline (intent, validator, builder, read-only executor).
- oneshot: the model sees the schema DDL plus the registry descriptions and writes one
  SQL query, which runs read-only. No validation, no retry.
- sql_agent: LangChain's SQL agent. Not built yet: simulating its multi-step tool calls
  needs one answer round per step (see builds/v01/log.md).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict
from sqlalchemy import Engine, MetaData, TextClause, text
from sqlalchemy.schema import CreateTable

from ledgerline.bench.items import EvalItem
from ledgerline.core.executor import ExecutionError, run
from ledgerline.core.registry import Registry
from ledgerline.llm.budget import BudgetGuard
from ledgerline.llm.errors import ParseError
from ledgerline.llm.gateway import Gateway
from ledgerline.llm.types import ChatMessage
from ledgerline.pipeline.service import AskService

ONESHOT_PROMPT_VERSION = "oneshot-v1"

ONESHOT_SYSTEM = """\
You answer business questions about one database by writing a single SQL query.

Return JSON with:
- "sql": one read-only SELECT statement for the database below, or null;
- "refusal_reason": null, or a short reason when the question cannot be answered from \
this database or asks to change data.

Use only the tables and columns in the schema. The reference date is {today}; write \
dates as literals relative to it. The SQL dialect is {dialect}.

Schema (DDL):
{ddl}

Descriptions:
{descriptions}
"""


class OneShotAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sql: str | None
    refusal_reason: str | None


@dataclass
class SystemAnswer:
    rows: list[tuple[Any, ...]]
    refused: bool
    error: str | None
    cost_usd: float
    latency_ms: float
    sql: str | None = None
    detail: dict[str, Any] = field(default_factory=dict[str, Any])
    provenance: dict[str, str] | None = None


class System(Protocol):
    name: str

    def answer(self, item: EvalItem, trial: int, guard: BudgetGuard | None) -> SystemAnswer: ...


class LedgerlineSystem:
    name = "ledgerline"

    def __init__(self, service: AskService, schema_id: str) -> None:
        self.service = service
        self.schema_id = schema_id
        service.reset_budget_per_ask = False

    def answer(self, item: EvalItem, trial: int, guard: BudgetGuard | None) -> SystemAnswer:
        if guard is not None and self.service.gateway.mode in ("live", "record"):
            self.service.gateway.guard = guard
        started = time.perf_counter()
        result = self.service.ask(
            self.schema_id,
            item.question,
            trial=trial,
            context={"system": self.name, "item_id": item.id, "trial": trial},
        )
        latency = (time.perf_counter() - started) * 1000
        error = None
        refused = result.refusal is not None
        if refused and result.refusal and result.refusal.startswith("the query failed"):
            error, refused = result.refusal, False
        attempts = result.validation.get("attempts", [])
        return SystemAnswer(
            rows=[tuple(r) for r in result.rows],
            refused=refused,
            error=error,
            cost_usd=result.cost_usd,
            latency_ms=latency,
            sql=result.sql,
            detail={
                "intent": result.intent,
                "refusal": result.refusal,
                "attempts": len(attempts),
                "issue_codes": sorted({i["code"] for a in attempts for i in a["issues"]}),
            },
            provenance=result.provenance,
        )


def raw_sql(sql: str) -> TextClause:
    """Model-written or gold SQL as-is: colons are escaped so SQLAlchemy never reads
    `:name` inside the query as a bind parameter."""
    return text(sql.replace(":", "\\:"))


def schema_ddl(engine: Engine) -> str:
    metadata = MetaData()
    metadata.reflect(engine)
    statements = [
        str(CreateTable(table).compile(dialect=engine.dialect)).strip() + ";"
        for table in metadata.sorted_tables
    ]
    return "\n\n".join(statements)


def registry_descriptions(registry: Registry) -> str:
    lines: list[str] = []
    for entity in registry.entities.values():
        if entity.description:
            lines.append(f"{entity.table}: {entity.description}")
        for fdef in entity.fields.values():
            if fdef.description:
                lines.append(f"{entity.table}.{fdef.column}: {fdef.description}")
    return "\n".join(lines) or "(none)"


class OneShotSystem:
    name = "oneshot"

    def __init__(
        self,
        gateway: Gateway,
        engine: Engine,
        registry: Registry,
        model: str,
        today: str,
        row_cap: int,
        timeout_s: float,
    ) -> None:
        self.gateway = gateway
        self.engine = engine
        self.model = model
        self.row_cap = row_cap
        self.timeout_s = timeout_s
        self.system_prompt = ONESHOT_SYSTEM.format(
            today=today,
            dialect=engine.dialect.name,
            ddl=schema_ddl(engine),
            descriptions=registry_descriptions(registry),
        )

    def answer(self, item: EvalItem, trial: int, guard: BudgetGuard | None) -> SystemAnswer:
        if guard is not None and self.gateway.mode in ("live", "record"):
            self.gateway.guard = guard
        version = ONESHOT_PROMPT_VERSION if trial == 1 else f"{ONESHOT_PROMPT_VERSION}+trial{trial}"
        messages = [
            ChatMessage(role="system", content=self.system_prompt),
            ChatMessage(role="user", content=item.question),
        ]
        started = time.perf_counter()
        try:
            result = self.gateway.complete(
                model=self.model,
                prompt_version=version,
                messages=messages,
                schema=OneShotAnswer,
                context={"system": self.name, "item_id": item.id, "trial": trial},
            )
        except ParseError as exc:
            return SystemAnswer(
                [],
                False,
                f"unparseable answer: {exc.reason}",
                0.0,
                (time.perf_counter() - started) * 1000,
            )
        answer = result.value
        if answer.sql is None or not answer.sql.strip():
            return SystemAnswer(
                [],
                True,
                None,
                result.cost_usd,
                (time.perf_counter() - started) * 1000,
                detail={"refusal": answer.refusal_reason},
                provenance=result.provenance,
            )
        try:
            rows = run(
                self.engine, raw_sql(answer.sql), timeout_s=self.timeout_s, row_cap=self.row_cap
            ).rows
            error = None
        except ExecutionError as exc:
            rows, error = [], str(exc)
        return SystemAnswer(
            rows,
            False,
            error,
            result.cost_usd,
            (time.perf_counter() - started) * 1000,
            sql=answer.sql,
            provenance=result.provenance,
        )
