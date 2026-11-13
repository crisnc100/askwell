"""Run the eval: every (schema, model, trial, system, item), checkpointed and budgeted.

A run lives in `evals/runs/<run_id>/` (gitignored): `results.jsonl` is the checkpoint,
so re-running the same run id resumes. In export mode, an item whose model request has
no recording is exported and left unfinished; import the answers and run again.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sqlalchemy import Engine

from askwell.bench.compare import results_match
from askwell.bench.items import (
    ROOT,
    EvalItem,
    default_gold,
    fieldservice_items,
    spider_items,
)
from askwell.bench.spider import schema_for
from askwell.bench.systems import AskwellSystem, OneShotSystem, System, raw_sql
from askwell.config import Settings
from askwell.core.executor import readonly_engine, run
from askwell.llm.budget import (
    BudgetGuard,
    Checkpoint,
    ItemDeferred,
    ItemResult,
    run_checkpointed,
)
from askwell.llm.simulate import PendingRequestError
from askwell.pipeline.service import AskService, SchemaConfig, build_gateway, load_schemas

# "ledgerline" is Askwell's system id, kept as recorded in the frozen reports and checkpoints.
SYSTEMS = ("ledgerline", "oneshot", "sql_agent")
RUNS_DIR = ROOT / "evals" / "runs"
EVAL_RECORDINGS = ROOT / "evals" / "recordings" / "eval"
EVAL_PENDING = ROOT / "evals" / "pending" / "eval"


@dataclass(frozen=True)
class Task:
    schema_id: str
    model: str
    trial: int
    system: str
    item: EvalItem
    prompt_version: str = ""
    registry_sha: str = ""

    @property
    def key(self) -> str:
        """The checkpoint key. It holds the prompt version, the registry's hash and a hash
        of everything that decides the item's score (question, gold SQL, category,
        ordering), so a result is reused only when none of them changed (a gold correction
        under the same item id is scored again)."""
        scored = json.dumps(
            [self.item.question, self.item.gold_sql, self.item.category, self.item.ordered]
        )
        item = hashlib.sha256(scored.encode()).hexdigest()
        key = (
            f"{self.schema_id}|{self.model}|t{self.trial}|{self.system}|{self.item.id}"
            f"|{self.prompt_version}|{self.registry_sha[:16]}|{item[:16]}"
        )
        # Only a second gold file adds its name, so default-gold runs still resume from
        # checkpoints written before --gold existed.
        if self.item.gold and self.item.gold != default_gold(self.schema_id):
            key += f"|gold={self.item.gold}"
        return key


def prompt_version_for(system: str) -> str:
    """The prompt version a system sends now (read at call time, never cached)."""
    from askwell.bench import systems as systems_module
    from askwell.pipeline import service as service_module

    if system == "ledgerline":
        return str(service_module.PROMPT_VERSION)
    return str(systems_module.ONESHOT_PROMPT_VERSION)


@dataclass
class RunResult:
    run_id: str
    records: list[dict[str, Any]]
    deferred: Counter[str] = field(default_factory=Counter[str])
    aborted: bool = False
    abort_reason: str | None = None
    spent_usd: float = 0.0
    registry_hashes: dict[str, str] = field(default_factory=dict[str, str])
    systems: list[str] = field(default_factory=list[str])
    models: list[str] = field(default_factory=list[str])
    trials: int = 1


def _schemas(
    settings: Settings, schema_ids: list[str]
) -> tuple[dict[str, SchemaConfig], dict[str, str]]:
    configured = load_schemas(settings)
    out: dict[str, SchemaConfig] = {}
    hashes: dict[str, str] = {}
    for schema_id in schema_ids:
        # A Spider schema is always regenerated and checked against its committed hash,
        # even if config/schemas.yaml also lists it: a hand-edited registry must never
        # reach the benchmark.
        if schema_id in configured and not schema_id.startswith("spider_"):
            out[schema_id] = configured[schema_id]
            continue
        if not schema_id.startswith("spider_"):
            raise ValueError(f"unknown schema {schema_id!r}")
        config, digest = schema_for(schema_id.removeprefix("spider_"))
        out[schema_id] = config
        hashes[schema_id] = digest
    return out, hashes


def items_for(schema_id: str, gold: Path | None = None) -> list[EvalItem]:
    if schema_id.startswith("spider_"):
        if gold is not None:
            raise ValueError(
                "Spider questions come from the pre-registered IDs; --gold is not used"
            )
        return spider_items(schema_id.removeprefix("spider_"))
    if schema_id == "fieldservice":
        return fieldservice_items(gold)
    raise ValueError(f"no gold set for schema {schema_id!r}")


def trials_for(schema_id: str, trials: int) -> int:
    """Fieldservice runs every trial asked for; Spider runs one (ADR-006)."""
    return trials if schema_id == "fieldservice" else 1


class _Gold:
    def __init__(self, engine: Engine, row_cap: int, timeout_s: float) -> None:
        self.engine = engine
        self.row_cap = row_cap
        self.timeout_s = timeout_s
        self._cache: dict[str, list[tuple[Any, ...]]] = {}

    def rows(self, item: EvalItem) -> list[tuple[Any, ...]]:
        assert item.gold_sql is not None
        if item.id not in self._cache:
            self._cache[item.id] = run(
                self.engine,
                raw_sql(item.gold_sql),
                timeout_s=self.timeout_s,
                row_cap=self.row_cap,
            ).rows
        return self._cache[item.id]


def score(
    item: EvalItem,
    rows: list[tuple[Any, ...]],
    refused: bool,
    error: str | None,
    gold: _Gold,
    row_cap: int,
) -> str:
    if refused:
        return "refused"
    if error is not None:
        return "error"
    if item.category != "in_schema":
        return "wrong"  # rows for a question that should have been refused
    ok = results_match(rows, gold.rows(item), ordered=item.ordered, row_cap=row_cap)
    return "correct" if ok else "wrong"


def run_eval(
    settings: Settings,
    *,
    run_id: str,
    schema_ids: list[str],
    systems: list[str],
    mode: str,
    models: list[str],
    trials: int,
    budget_usd: float,
    progress: Callable[[str], None] = lambda _m: None,
    gold: Path | None = None,
) -> RunResult:
    """`gold` scores a second gold file for the one schema given, in place of its
    default gold set."""
    if gold is not None and len(schema_ids) != 1:
        raise ValueError("--gold takes exactly one schema")
    for system in systems:
        if system not in SYSTEMS:
            raise ValueError(f"unknown system {system!r}")
        if system == "sql_agent":
            raise NotImplementedError(
                "sql_agent is deferred: it needs a live model (multi-step tool calls "
                "can't be honestly simulated in one pass)"
            )
    schemas, hashes = _schemas(settings, schema_ids)
    registry_sha = {
        schema_id: hashlib.sha256(config.registry_path.read_bytes()).hexdigest()
        for schema_id, config in schemas.items()
    }
    tasks = [
        Task(
            schema_id,
            model,
            trial,
            system,
            item,
            prompt_version_for(system),
            registry_sha[schema_id],
        )
        for schema_id in schema_ids
        for model in models
        for trial in range(1, trials_for(schema_id, trials) + 1)
        for system in systems
        for item in (items_for(schema_id) if gold is None else items_for(schema_id, gold))
    ]
    engines: dict[str, Engine] = {}
    golds: dict[str, _Gold] = {}
    built: dict[tuple[str, str, str], System] = {}

    def engine(schema_id: str) -> Engine:
        if schema_id not in engines:
            engines[schema_id] = readonly_engine(schemas[schema_id].db_url)
            golds[schema_id] = _Gold(engines[schema_id], settings.row_cap, settings.query_timeout_s)
        return engines[schema_id]

    def system_for(task: Task) -> System:
        key = (task.schema_id, task.system, task.model)
        if key not in built:
            store = EVAL_RECORDINGS / task.schema_id / f"{task.system}.jsonl"
            pending = EVAL_PENDING / task.schema_id / task.system
            gateway = build_gateway(
                settings, mode, store_path=store, pending_dir=pending, budget_usd=budget_usd
            )
            if task.system == "ledgerline":
                service = AskService(
                    settings,
                    {task.schema_id: schemas[task.schema_id]},
                    gateway,
                    audit=None,
                    model=task.model,
                )
                service.use_engine(task.schema_id, engine(task.schema_id))
                built[key] = AskwellSystem(service, task.schema_id)
            else:
                service = AskService(
                    settings,
                    {task.schema_id: schemas[task.schema_id]},
                    gateway,
                    audit=None,
                    model=task.model,
                )
                built[key] = OneShotSystem(
                    gateway,
                    engine(task.schema_id),
                    service.registry(task.schema_id),
                    task.model,
                    settings.now.date().isoformat(),
                    settings.row_cap,
                    settings.query_timeout_s,
                )
        return built[key]

    deferred: Counter[str] = Counter()

    def work(task: Task, guard: BudgetGuard) -> ItemResult:
        system = system_for(task)
        try:
            answer = system.answer(task.item, task.trial, guard)
        except PendingRequestError as exc:
            deferred[f"{task.schema_id}/{task.system}"] += 1
            raise ItemDeferred(task.key) from exc
        outcome = score(
            task.item,
            answer.rows,
            answer.refused,
            answer.error,
            golds[task.schema_id],
            settings.row_cap,
        )
        record = {
            "key": task.key,
            "schema_id": task.schema_id,
            "model": task.model,
            "trial": task.trial,
            "system": task.system,
            "item_id": task.item.id,
            "gold": task.item.gold,
            "category": task.item.category,
            "difficulty": task.item.difficulty,
            "outcome": outcome,
            "cost_usd": answer.cost_usd,
            "latency_ms": answer.latency_ms,
            "error": answer.error,
            "sql": answer.sql,
            "detail": answer.detail,
            "provenance": answer.provenance,
        }
        progress(f"{task.key}: {outcome}")
        return ItemResult(record=record, cost_usd=answer.cost_usd)

    run_dir = RUNS_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "config.json").write_text(
        json.dumps(
            {
                "schemas": schema_ids,
                "systems": systems,
                "mode": mode,
                "models": models,
                "trials": trials,
                "budget_usd": budget_usd,
                "gold": str(gold) if gold is not None else None,
                "registry_hashes": hashes,
            },
            indent=2,
        )
        + "\n"
    )
    try:
        outcome = run_checkpointed(
            tasks, lambda t: t.key, work, Checkpoint(run_dir / "results.jsonl"), budget_usd
        )
    finally:
        for eng in engines.values():
            eng.dispose()
    return RunResult(
        run_id=run_id,
        records=outcome.records,
        deferred=deferred,
        aborted=outcome.aborted,
        abort_reason=outcome.abort_reason,
        spent_usd=outcome.spent_usd,
        registry_hashes=hashes,
        systems=systems,
        models=models,
        trials=trials,
    )


def pending_counts() -> dict[str, int]:
    """Exported, unanswered requests per schema/system directory."""
    counts: dict[str, int] = {}
    if not EVAL_PENDING.exists():
        return counts
    for directory in sorted(p for p in EVAL_PENDING.glob("*/*") if p.is_dir()):
        n = sum(1 for f in directory.glob("*.json") if not f.name.endswith(".answer.json"))
        if n:
            counts[str(directory.relative_to(EVAL_PENDING))] = n
    return counts


def default_run_dir(run_id: str) -> Path:
    return RUNS_DIR / run_id
