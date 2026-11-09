"""The ask service: schemas, the model gateway, the graph, the executor and the audit."""

from __future__ import annotations

import json
import logging
import os
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import Engine, create_engine

from ledgerline.config import Settings
from ledgerline.core.audit import AuditEntry, AuditLog
from ledgerline.core.executor import Executor, readonly_engine
from ledgerline.core.intent import Intent
from ledgerline.core.registry import Registry, load_registry
from ledgerline.core.validate import QueryPlan, ValidationResult, validate
from ledgerline.llm.budget import BudgetGuard
from ledgerline.llm.gateway import Gateway, OpenRouterTransport
from ledgerline.llm.pricing import PriceBook
from ledgerline.llm.replay import ReplayStore
from ledgerline.llm.types import ChatMessage, LLMResult
from ledgerline.pipeline.graph import AskState, build_graph
from ledgerline.pipeline.prompt import PROMPT_VERSION, first_messages, registry_view

log = logging.getLogger("ledgerline.ask")

ROOT = Path(__file__).resolve().parents[2]
SCHEMAS_FILE = ROOT / "config" / "schemas.yaml"
RECORDINGS_FILE = "interpret.jsonl"


class UnknownSchemaError(KeyError):
    pass


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

    `db_url_env` names an environment variable; LEDGERLINE_* variables fall back to the
    matching setting (so the default compose URLs work without a .env)."""
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    out: dict[str, SchemaConfig] = {}
    for schema_id, entry in (data.get("schemas") or {}).items():
        env = str(entry["db_url_env"])
        url = os.environ.get(env)
        if url is None and env.startswith("LEDGERLINE_"):
            url = getattr(settings, env.removeprefix("LEDGERLINE_").lower(), None)
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


def build_gateway(settings: Settings, mode: str | None = None) -> Gateway:
    chosen = mode or settings.llm_mode
    store = ReplayStore(ROOT / settings.replay_dir / RECORDINGS_FILE)
    if chosen in ("replay", "export"):
        return Gateway(
            mode=chosen,  # type: ignore[arg-type]
            store=store,
            transport=None,
            price_lookup=lambda _m: None,
            guard=None,
            max_tokens=settings.max_tokens,
            pending_dir=ROOT / settings.pending_dir,
        )
    book = PriceBook.fetch(settings.openrouter_base_url)
    return Gateway(
        mode=chosen,  # type: ignore[arg-type]
        store=store,
        transport=OpenRouterTransport(settings),
        price_lookup=book.get,
        guard=BudgetGuard(settings.ask_budget_usd),
        max_tokens=settings.max_tokens,
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
            raise ValueError("no model configured (LEDGERLINE_DEFAULT_MODEL)")
        self.settings = settings
        self.schemas = schemas
        self.gateway = gateway
        self.audit = audit
        self.model = chosen
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

    def close(self) -> None:
        for engine in self._engines.values():
            engine.dispose()
        self._engines.clear()

    def ask(self, schema_id: str, question: str) -> AskResult:
        registry = self.registry(schema_id)
        config = self.schemas[schema_id]
        trace_id = str(uuid.uuid4())
        view = registry_view(registry, self.settings.now, self.settings.prompt_budget_chars)
        for step in view.truncation:
            log.info("prompt truncation for %s: %s", schema_id, step)
        if self.gateway.mode in ("live", "record"):
            self.gateway.guard = BudgetGuard(self.settings.ask_budget_usd)
        context = {"schema_id": schema_id, "question": question}

        def interpret(messages: list[ChatMessage]) -> LLMResult[Intent]:
            return self.gateway.complete(
                model=self.model,
                prompt_version=PROMPT_VERSION,
                messages=messages,
                schema=Intent,
                context=context,
            )

        def check(intent: Intent) -> ValidationResult:
            return validate(
                intent,
                registry,
                now=self.settings.now,
                allow_draft=config.allow_draft,
                row_cap=self.settings.row_cap,
            )

        executor = Executor(
            self.engine(schema_id),
            audit=self.audit,
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

        graph = build_graph(interpret, check, execute)
        state: AskState = graph.invoke(
            {"question": question, "messages": first_messages(view, question), "attempts": []}
        )
        return self._result(schema_id, question, trace_id, state, view.truncation)

    def _result(
        self,
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
        if execution is None and self.audit is not None and error is None:
            # Answered and failed executions are audited by the executor; refusals here.
            self.audit.record(
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
        )


def _intent_json(state: AskState) -> str:
    intent = state.get("intent")
    return intent.model_dump_json(exclude_defaults=True) if intent else "null"


def _validation(state: AskState) -> dict[str, Any]:
    attempts = state.get("attempts", [])
    return {"ok": state.get("plan") is not None, "attempts": attempts}
