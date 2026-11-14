"""The ask service: schemas, the model gateway, the graph, the executor and the audit."""

from __future__ import annotations

import json
import logging
import os
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import Engine, create_engine

from askwell.config import Settings
from askwell.core.audit import AuditEntry, AuditLog
from askwell.core.executor import Executor, readonly_engine
from askwell.core.intent import Intent
from askwell.core.registry import Registry, load_registry
from askwell.core.validate import QueryPlan, ValidationResult, validate
from askwell.llm.budget import BudgetGuard
from askwell.llm.daily import DailySpend
from askwell.llm.errors import ReplayMissError
from askwell.llm.gateway import Gateway
from askwell.llm.pricing import PriceBook
from askwell.llm.providers import ProviderRouter
from askwell.llm.replay import ReplayStore
from askwell.llm.simulate import PendingRequestError, register_response_model
from askwell.llm.types import ChatMessage, LLMResult
from askwell.pipeline.graph import AskState, build_graph
from askwell.pipeline.prompt import PROMPT_VERSION, first_messages, registry_view

log = logging.getLogger("askwell.ask")
register_response_model(Intent)

ROOT = Path(__file__).resolve().parents[2]
SCHEMAS_FILE = ROOT / "config" / "schemas.yaml"
RECORDINGS_FILE = "interpret.jsonl"


class UnknownSchemaError(KeyError):
    pass


@dataclass(frozen=True)
class AskTarget:
    """Everything one ask runs against. A configured schema and an uploaded workspace
    both become one of these, so they share the whole pipeline.

    `now` is the reference time relative dates resolve against: the pinned
    `ASKWELL_NOW` for configured schemas (so evals reproduce), or the wall clock in
    the workspace's time zone, as a naive local time, for a workspace. `time_zone` is
    the label the prompt gives that time."""

    schema_id: str
    registry: Registry
    engine: Engine
    allow_draft: bool
    now: datetime
    time_zone: str
    audit: AuditLog | None


@dataclass(frozen=True)
class SchemaConfig:
    id: str
    title: str
    registry_path: Path
    db_url: str
    allow_draft: bool = False
    examples: list[str] = field(default_factory=list[str])


def load_schemas(settings: Settings, path: Path = SCHEMAS_FILE) -> dict[str, SchemaConfig]:
    """`config/schemas.yaml`: schema id -> registry path, DB URL env var, examples.

    `db_url_env` names an environment variable; ASKWELL_* variables fall back to the
    matching setting (so the default compose URLs work without a .env)."""
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    out: dict[str, SchemaConfig] = {}
    for schema_id, entry in (data.get("schemas") or {}).items():
        env = str(entry["db_url_env"])
        url = os.environ.get(env)
        if url is None and env.startswith("ASKWELL_"):
            url = getattr(settings, env.removeprefix("ASKWELL_").lower(), None)
        if url is None:
            raise ValueError(f"schema {schema_id}: {env} is not set")
        registry_path = Path(entry["registry"])
        out[schema_id] = SchemaConfig(
            id=schema_id,
            title=str(entry.get("title", schema_id)),
            registry_path=registry_path if registry_path.is_absolute() else ROOT / registry_path,
            db_url=str(url),
            allow_draft=bool(entry.get("allow_draft", False)),
            examples=[str(q) for q in entry.get("examples") or []],
        )
    return out


def daily_spend(settings: Settings) -> DailySpend | None:
    """The global daily cap, when one is configured. Every live gateway shares it."""
    if settings.daily_spend_cap_usd is None:
        return None
    return DailySpend(ROOT / settings.spend_db, settings.daily_spend_cap_usd)


def build_gateway(
    settings: Settings,
    mode: str | None = None,
    *,
    store_path: Path | None = None,
    pending_dir: Path | None = None,
    budget_usd: float | None = None,
) -> Gateway:
    """A gateway for `mode`. The eval passes its own store and pending directory so each
    schema and system keeps separate recordings."""
    chosen = mode or settings.llm_mode
    store = ReplayStore(store_path or ROOT / settings.replay_dir / RECORDINGS_FILE)
    if chosen in ("replay", "export"):
        return Gateway(
            mode=chosen,  # type: ignore[arg-type]
            store=store,
            transport=None,
            price_lookup=lambda _m: None,
            guard=None,
            max_tokens=settings.max_tokens,
            pending_dir=pending_dir or ROOT / settings.pending_dir,
        )
    router = ProviderRouter(
        settings, load_openrouter_prices=lambda: PriceBook.fetch(settings.openrouter_base_url)
    )
    return Gateway(
        mode=chosen,  # type: ignore[arg-type]
        store=store,
        transport=router,
        price_lookup=router.price,
        guard=BudgetGuard(budget_usd if budget_usd is not None else settings.ask_budget_usd),
        max_tokens=settings.max_tokens,
        daily=daily_spend(settings),
        live_answers_off=settings.live_answers_off,
    )


def _jsonable(value: Any) -> Any:
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return value


@dataclass
class AskResult:
    trace_id: str
    schema_id: str
    question: str
    intent: dict[str, Any] | None
    validation: dict[str, Any]
    sql: str | None
    params: dict[str, Any] | None
    columns: list[str]
    rows: list[list[Any]]
    truncated: bool
    refusal: str | None
    cost_usd: float
    model: str
    provenance: dict[str, str] | None
    prompt_truncation: list[str]
    tied_at_cutoff: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "schema_id": self.schema_id,
            "question": self.question,
            "intent": self.intent,
            "validation": self.validation,
            "sql": self.sql,
            "params": {k: _jsonable(v) for k, v in (self.params or {}).items()}
            if self.params is not None
            else None,
            "columns": self.columns,
            "rows": [[_jsonable(v) for v in row] for row in self.rows],
            "truncated": self.truncated,
            "tied_at_cutoff": self.tied_at_cutoff,
            "refusal": self.refusal,
            "cost_usd": self.cost_usd,
            "model": self.model,
            "provenance": self.provenance,
            "prompt_truncation": self.prompt_truncation,
        }


class AskService:
    def __init__(
        self,
        settings: Settings,
        schemas: dict[str, SchemaConfig],
        gateway: Gateway,
        audit: AuditLog | None,
        model: str | None = None,
    ) -> None:
        chosen = model or settings.default_model
        if chosen is None:
            raise ValueError("no model configured (ASKWELL_DEFAULT_MODEL)")
        self.settings = settings
        self.schemas = schemas
        self.gateway = gateway
        self.audit = audit
        self.model = chosen
        # The API gives each ask its own budget; an eval run shares one guard instead.
        self.reset_budget_per_ask = True
        self._registries: dict[str, Registry] = {}
        self._engines: dict[str, Engine] = {}

    @classmethod
    def from_settings(cls, settings: Settings, mode: str | None = None) -> AskService:
        audit = AuditLog(create_engine(settings.app_database_url))
        return cls(settings, load_schemas(settings), build_gateway(settings, mode), audit)

    def registry(self, schema_id: str) -> Registry:
        if schema_id not in self.schemas:
            raise UnknownSchemaError(schema_id)
        if schema_id not in self._registries:
            self._registries[schema_id] = load_registry(self.schemas[schema_id].registry_path)
        return self._registries[schema_id]

    def engine(self, schema_id: str) -> Engine:
        if schema_id not in self._engines:
            self._engines[schema_id] = readonly_engine(self.schemas[schema_id].db_url)
        return self._engines[schema_id]

    def use_engine(self, schema_id: str, engine: Engine) -> None:
        """Share an engine the caller already opened (the eval reuses one per schema)."""
        self._engines[schema_id] = engine

    def close(self) -> None:
        for engine in self._engines.values():
            engine.dispose()
        self._engines.clear()

    def ask(
        self,
        schema_id: str,
        question: str,
        *,
        trial: int = 1,
        context: dict[str, Any] | None = None,
    ) -> AskResult:
        """Answer one question. `trial` > 1 asks again as an independent sample: it is
        part of the prompt version, so it gets its own recording.

        This is the one place that guarantees every ask exactly one audit row. The paths
        inside (answered, refused, query error, budget stop) write their own row; any
        failure that leaves before one was written (a missing registry or database, a
        gateway or recording error) gets an error row here, then is re-raised so the
        API status and CLI exit code stay the same."""
        return self._audited(
            schema_id, self.audit, lambda: self.target(schema_id), question, trial, context
        )

    def target(self, schema_id: str) -> AskTarget:
        """The ask target for a schema in `config/schemas.yaml`."""
        registry = self.registry(schema_id)
        return AskTarget(
            schema_id=schema_id,
            registry=registry,
            engine=self.engine(schema_id),
            allow_draft=self.schemas[schema_id].allow_draft,
            now=self.settings.now,
            time_zone="UTC",
            audit=self.audit,
        )

    def ask_target(
        self,
        target: AskTarget,
        question: str,
        *,
        trial: int = 1,
        context: dict[str, Any] | None = None,
    ) -> AskResult:
        """`ask`, for a target the caller built (an uploaded workspace)."""
        return self._audited(
            target.schema_id, target.audit, lambda: target, question, trial, context
        )

    def _audited(
        self,
        schema_id: str,
        audit_log: AuditLog | None,
        build: Callable[[], AskTarget],
        question: str,
        trial: int,
        context: dict[str, Any] | None,
    ) -> AskResult:
        trace_id = str(uuid.uuid4())
        audit = _OneRow(audit_log)
        # A fresh guard per ask, held here rather than on the shared gateway, so
        # concurrent requests never reset or charge each other's budget. (The eval turns
        # this off and shares one run-wide guard through gateway.guard.) The guard is
        # charged when a call is paid for, so its total is the ask's spend even when a
        # later step fails.
        ask_guard = (
            BudgetGuard(self.settings.ask_budget_usd)
            if self.gateway.mode in ("live", "record") and self.reset_budget_per_ask
            else None
        )
        try:
            return self._ask(build(), question, trace_id, audit, ask_guard, trial, context)
        except Exception as exc:
            if not audit.written:
                spent = ask_guard.spent_usd if ask_guard is not None else 0.0
                try:
                    self._audit_failure(audit, schema_id, question, trace_id, exc, spent)
                except Exception:
                    # Never let a broken audit database hide the error that matters.
                    log.exception("could not write the audit row for ask %s", trace_id)
            raise

    def _ask(
        self,
        target: AskTarget,
        question: str,
        trace_id: str,
        audit: _OneRow,
        ask_guard: BudgetGuard | None,
        trial: int,
        context: dict[str, Any] | None,
    ) -> AskResult:
        schema_id = target.schema_id
        registry = target.registry
        view = registry_view(
            registry,
            target.now,
            self.settings.prompt_budget_chars,
            target.time_zone,
            self.settings.features,
        )
        for step in view.truncation:
            log.info("prompt truncation for %s: %s", schema_id, step)
        prompt_version = PROMPT_VERSION if trial == 1 else f"{PROMPT_VERSION}+trial{trial}"
        request_context = {"schema_id": schema_id, "question": question, **(context or {})}

        def interpret(messages: list[ChatMessage]) -> LLMResult[Intent]:
            return self.gateway.complete(
                guard=ask_guard,
                model=self.model,
                prompt_version=prompt_version,
                messages=messages,
                schema=Intent,
                context=request_context,
            )

        def check(intent: Intent) -> ValidationResult:
            return validate(
                intent,
                registry,
                now=target.now,
                allow_draft=target.allow_draft,
                row_cap=self.settings.row_cap,
                features=self.settings.features,
            )

        executor = Executor(
            target.engine,
            audit=audit if audit.enabled else None,
            timeout_s=self.settings.query_timeout_s,
            row_cap=self.settings.row_cap,
        )

        def execute(plan: QueryPlan, state: AskState) -> Any:
            return executor.execute(
                plan,
                question=question,
                intent_json=_intent_json(state),
                validation_json=json.dumps(_validation(state)),
                schema_id=schema_id,
                cost_usd=state.get("cost_usd", 0.0),
                model=self.model,
                trace_id=trace_id,
            )

        graph = build_graph(interpret, check, execute, refuse_on_budget=self.reset_budget_per_ask)
        state: AskState = graph.invoke(
            {"question": question, "messages": first_messages(view, question), "attempts": []}
        )
        return self._result(audit, schema_id, question, trace_id, state, view.truncation)

    def _audit_failure(
        self,
        audit: _OneRow,
        schema_id: str,
        question: str,
        trace_id: str,
        exc: Exception,
        cost_usd: float,
    ) -> None:
        reason = _failure_reason(exc)
        audit.record(
            AuditEntry(
                trace_id=trace_id,
                schema_id=schema_id,
                question=question,
                intent="null",
                validation=json.dumps({"ok": False, "error": reason}),
                sql=None,
                params_hash=None,
                row_count=None,
                cost_usd=cost_usd,
                model=self.model,
                outcome="error",
            )
        )

    def _result(
        self,
        audit: _OneRow,
        schema_id: str,
        question: str,
        trace_id: str,
        state: AskState,
        truncation: list[str],
    ) -> AskResult:
        execution = state.get("execution")
        refusal = state.get("refusal")
        error = state.get("execution_error")
        if error is not None:
            refusal = f"the query failed: {error}"
        intent = state.get("intent")
        validation = _validation(state)
        if execution is None and error is None:
            # Answered and failed executions are audited by the executor; refusals here.
            audit.record(
                AuditEntry(
                    trace_id=trace_id,
                    schema_id=schema_id,
                    question=question,
                    intent=_intent_json(state),
                    validation=json.dumps(validation),
                    sql=None,
                    params_hash=None,
                    row_count=None,
                    cost_usd=state.get("cost_usd", 0.0),
                    model=self.model,
                    outcome="refused",
                )
            )
        return AskResult(
            trace_id=trace_id,
            schema_id=schema_id,
            question=question,
            intent=intent.model_dump(mode="json", exclude_defaults=True) if intent else None,
            validation=validation,
            sql=execution.sql if execution else None,
            params=execution.params if execution else None,
            columns=execution.result.columns if execution else [],
            rows=[list(r) for r in execution.result.rows] if execution else [],
            truncated=execution.result.truncated if execution else False,
            refusal=None if execution else refusal,
            cost_usd=state.get("cost_usd", 0.0),
            model=self.model,
            provenance=state.get("provenance"),
            prompt_truncation=truncation,
            tied_at_cutoff=execution.tied_at_cutoff if execution else False,
        )


class _OneRow:
    """The audit log as seen by one ask: it remembers whether that ask's row was written,
    so `ask` can add the error row exactly when no other path wrote one."""

    def __init__(self, log: AuditLog | None) -> None:
        self.log = log
        self.written = False

    @property
    def enabled(self) -> bool:
        return self.log is not None

    def record(self, entry: AuditEntry) -> None:
        if self.log is None:
            return
        self.log.record(entry)
        self.written = True


def _failure_reason(exc: Exception) -> str:
    """A short reason for the audit row. The exception's message is left out (a provider
    or driver message can carry request details); its type is enough to find the
    failure in the logs."""
    if isinstance(exc, PendingRequestError):
        return "no recording; the model request was exported for a simulated answer"
    if isinstance(exc, ReplayMissError):
        return "no recorded model answer (replay mode)"
    return f"ask failed: {type(exc).__name__}"


def _intent_json(state: AskState) -> str:
    intent = state.get("intent")
    return intent.model_dump_json(exclude_defaults=True) if intent else "null"


def _validation(state: AskState) -> dict[str, Any]:
    attempts = state.get("attempts", [])
    out: dict[str, Any] = {"ok": state.get("plan") is not None, "attempts": attempts}
    if state.get("budget_stopped"):
        out["stopped"] = state.get("refusal")
    return out
