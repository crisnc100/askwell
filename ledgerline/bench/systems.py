"""The systems under test. Each one answers an item with rows, a refusal or an error.

- ledgerline: the full pipeline (intent, validator, builder, read-only executor).
- oneshot: the model sees the schema DDL plus the registry descriptions and writes one
  SQL query, which runs read-only. No validation, no retry.
- sql_agent: LangChain's SQL agent. Deferred until there is a live model: its
  multi-step tool calls can't be honestly simulated in one pass.
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
from ledgerline.llm.simulate import register_response_model
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


register_response_model(OneShotAnswer)


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
                "attempt_provenance": [a.get("provenance") for a in attempts],
            },
            provenance=result.provenance,
        )


class UnsafeSqlError(ValueError):
    """Model-written SQL that is not exactly one SELECT (or WITH ... SELECT)."""


def single_select(sql: str) -> str:
    """Return `sql` if it is exactly one SELECT or WITH statement, else raise.

    Model SQL is untrusted. A batch such as "ROLLBACK; BEGIN READ WRITE; ..." would end
    the read-only transaction and run anything after it, so a second statement is never
    allowed. The scan skips quoted strings ('...', "...", $tag$...$tag$) and comments
    (-- and /* */), allows one trailing semicolon (and a comment after it), and requires
    the first word to be SELECT or WITH. This is the early, friendly refusal; the real
    guarantee is the driver: run(..., untrusted=True) executes through a path that
    accepts only one statement."""
    i, n = 0, len(sql)
    code: list[str] = []  # the SQL with strings blanked and comments removed
    last_code_end = 0  # index just past the last character that is code, not comment
    while i < n:
        ch = sql[i]
        if sql.startswith("--", i):
            end = sql.find("\n", i)
            i = n if end == -1 else end
            code.append(" ")
        elif sql.startswith("/*", i):
            end = sql.find("*/", i + 2)
            if end == -1:
                raise UnsafeSqlError("unclosed comment")
            i = end + 2
            code.append(" ")
        elif ch in ("'", '"'):
            end = i + 1
            while True:
                end = sql.find(ch, end)
                if end == -1:
                    raise UnsafeSqlError("unclosed quote")
                if sql.startswith(ch * 2, end):  # doubled quote inside the string
                    end += 2
                    continue
                break
            i = end + 1
            code.append(" x ")
            last_code_end = i
        elif ch == "$":
            tag_end = sql.find("$", i + 1)
            tag = sql[i : tag_end + 1] if tag_end != -1 else ""
            if tag and (tag == "$$" or tag[1:-1].replace("_", "").isalnum()):
                end = sql.find(tag, tag_end + 1)
                if end == -1:
                    raise UnsafeSqlError("unclosed dollar quote")
                i = end + len(tag)
                code.append(" x ")
                last_code_end = i
            else:
                code.append(ch)
                i += 1
                last_code_end = i
        else:
            code.append(ch)
            i += 1
            if not ch.isspace():
                last_code_end = i
    body = "".join(code).strip()
    closing = body.endswith(";")
    if closing:
        body = body[:-1].rstrip()
    if not body:
        raise UnsafeSqlError("no statement")
    if ";" in body:
        raise UnsafeSqlError("only a single statement is allowed")
    first = body.split(None, 1)[0].lower()
    if first not in ("select", "with"):
        raise UnsafeSqlError(f"only a single SELECT is allowed, not {first.upper()}")
    # The statement itself: up to the last code character, minus a closing semicolon and
    # any comment after it.
    statement = sql[:last_code_end].strip()
    return statement[:-1].rstrip() if closing else statement


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
                exc.cost_usd,
                (time.perf_counter() - started) * 1000,
                provenance=exc.provenance,
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
            query = single_select(answer.sql)
            rows = run(
                self.engine,
                raw_sql(query),
                timeout_s=self.timeout_s,
                row_cap=self.row_cap,
                untrusted=True,  # the driver, not just single_select, allows one statement
            ).rows
            error = None
        except UnsafeSqlError as exc:
            rows, error = [], f"refused model SQL: {exc}"
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
