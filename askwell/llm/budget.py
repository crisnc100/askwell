"""Hard per-run budgets, 429 backoff, and checkpointed runs that resume.

A run appends one JSON line per finished item to its results file. Re-running
with the same file skips finished items and carries their spend forward, so the
budget covers the whole run across resumes. When the budget stops a run, the
outcome is marked partial and still holds every finished record.
"""

from __future__ import annotations

import json
import os
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from askwell.llm.errors import BudgetExceededError, RateLimitedError


class ItemDeferred(Exception):  # noqa: N818 - a signal, not an error
    """Raised by `work` when an item cannot finish yet (e.g. its model request was
    exported for a simulated answer). The item is not checkpointed; a later run retries."""


class BudgetGuard:
    def __init__(self, limit_usd: float, spent_usd: float = 0.0) -> None:
        if limit_usd < 0:
            raise ValueError("budget must be >= 0")
        self.limit_usd = limit_usd
        self.spent_usd = spent_usd

    @property
    def remaining_usd(self) -> float:
        return self.limit_usd - self.spent_usd

    def precheck(self, worst_case_usd: float) -> None:
        """Refuse a call whose worst-case cost could cross the limit."""
        if self.spent_usd + worst_case_usd > self.limit_usd:
            raise BudgetExceededError(self.spent_usd, worst_case_usd, self.limit_usd)

    def charge(self, cost_usd: float) -> None:
        self.spent_usd += cost_usd


def is_rate_limit(exc: BaseException) -> bool:
    if getattr(exc, "status_code", None) == 429:
        return True
    response = getattr(exc, "response", None)
    return getattr(response, "status_code", None) == 429


def with_backoff[T](
    call: Callable[[], T],
    *,
    retries: int = 5,
    base_delay_s: float = 1.0,
    max_delay_s: float = 30.0,
    sleep: Callable[[float], None] = time.sleep,
) -> T:
    """Run `call`, retrying only HTTP 429s with exponential backoff."""
    for attempt in range(retries + 1):
        try:
            return call()
        except Exception as exc:
            if not is_rate_limit(exc):
                raise
            if attempt == retries:
                raise RateLimitedError(f"still rate limited after {retries} retries") from exc
            sleep(min(max_delay_s, base_delay_s * 2**attempt))
    raise AssertionError("unreachable")


class Checkpoint:
    """Append-only JSONL. Each line is one of:

    - a finished item: `{"key", "cost_usd", "record"}`
    - spend from an unfinished item (budget stop or crash): `{"key", "cost_usd",
      "record": null}`. It is not "done", but its cost still counts on resume.
    """

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)

    def load(self) -> tuple[dict[str, dict[str, Any]], float]:
        """Return (finished entries by key, total spend recorded so far).

        A torn final line (a run killed mid-write: no trailing newline, not valid JSON)
        is cut off the file, so later appends start on a clean line. Any other line that
        is not valid JSON is skipped, never treated as the end of the file."""
        done: dict[str, dict[str, Any]] = {}
        spent = 0.0
        if not self.path.exists():
            return done, spent
        self._repair_torn_tail()
        with self.path.open(encoding="utf-8") as fh:
            for line in fh:
                if not line.strip():
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                spent += float(entry["cost_usd"])
                if entry["record"] is not None:
                    done[entry["key"]] = entry
        return done, spent

    def _repair_torn_tail(self) -> None:
        data = self.path.read_bytes()
        if not data or data.endswith(b"\n"):
            return
        start = data.rfind(b"\n") + 1
        try:
            json.loads(data[start:])
        except json.JSONDecodeError:
            with self.path.open("r+b") as fh:
                fh.truncate(start)
            return
        with self.path.open("ab") as fh:  # complete line, missing only its newline
            fh.write(b"\n")

    def append(self, key: str, cost_usd: float, record: dict[str, Any] | None) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps({"key": key, "cost_usd": cost_usd, "record": record}, sort_keys=True)
        with self.path.open("a+b") as fh:
            # Never glue a record onto a torn line: start on a fresh line if needed.
            fh.seek(0, os.SEEK_END)
            prefix = b""
            if fh.tell() > 0:
                fh.seek(-1, os.SEEK_END)
                if fh.read(1) != b"\n":
                    prefix = b"\n"
            fh.write(prefix + line.encode("utf-8") + b"\n")
            fh.flush()
            os.fsync(fh.fileno())


@dataclass
class RunOutcome:
    records: list[dict[str, Any]] = field(default_factory=list[dict[str, Any]])
    resumed: int = 0
    newly_completed: int = 0
    total_items: int = 0
    spent_usd: float = 0.0
    deferred: int = 0
    aborted: bool = False
    abort_reason: str | None = None

    @property
    def is_partial(self) -> bool:
        return len(self.records) < self.total_items


@dataclass
class ItemResult:
    record: dict[str, Any]
    cost_usd: float


def run_checkpointed[T](
    items: Sequence[T],
    key: Callable[[T], str],
    work: Callable[[T, BudgetGuard], ItemResult],
    checkpoint: Checkpoint,
    budget_usd: float,
) -> RunOutcome:
    """Run `work` over `items`, resuming from `checkpoint` and stopping at the budget.

    `work` must pre-check and charge the guard for each call it makes (the gateway
    does). The budget is the run's total: spend already in the checkpoint counts.
    """
    done, already_spent = checkpoint.load()
    guard = BudgetGuard(budget_usd, spent_usd=already_spent)
    outcome = RunOutcome(total_items=len(items))
    for item in items:
        item_key = key(item)
        if item_key in done:
            outcome.records.append(done[item_key]["record"])
            outcome.resumed += 1
            continue
        spent_before = guard.spent_usd
        try:
            result = work(item, guard)
        except BudgetExceededError as exc:
            _record_unfinished_spend(checkpoint, item_key, guard.spent_usd - spent_before)
            outcome.aborted = True
            outcome.abort_reason = str(exc)
            break
        except ItemDeferred:
            _record_unfinished_spend(checkpoint, item_key, guard.spent_usd - spent_before)
            outcome.deferred += 1
            continue
        except BaseException:
            _record_unfinished_spend(checkpoint, item_key, guard.spent_usd - spent_before)
            raise
        # Count the larger of what the guard saw and what `work` reports, so spend
        # that bypassed the guard still reaches the budget and the checkpoint.
        seen = guard.spent_usd - spent_before
        if result.cost_usd > seen:
            guard.charge(result.cost_usd - seen)
        cost = guard.spent_usd - spent_before
        checkpoint.append(item_key, cost, result.record)
        outcome.records.append(result.record)
        outcome.newly_completed += 1
    outcome.spent_usd = guard.spent_usd
    return outcome


def _record_unfinished_spend(checkpoint: Checkpoint, key: str, spent: float) -> None:
    if spent > 0:
        checkpoint.append(key, spent, None)
