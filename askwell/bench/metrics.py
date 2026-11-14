"""Eval metrics with Wilson 95% intervals (the list in ADR-006)."""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from typing import Any, Literal

Outcome = Literal["correct", "wrong", "refused", "error", "pending"]
Z95 = 1.959963984540054


def wilson(successes: int, total: int) -> tuple[float, float] | None:
    """The Wilson score interval for successes/total at 95%, or None when total is 0."""
    if total == 0:
        return None
    p = successes / total
    denominator = 1 + Z95**2 / total
    centre = (p + Z95**2 / (2 * total)) / denominator
    half = Z95 * math.sqrt(p * (1 - p) / total + Z95**2 / (4 * total**2)) / denominator
    return max(0.0, centre - half), min(1.0, centre + half)


@dataclass(frozen=True)
class Rate:
    numerator: int
    denominator: int

    @property
    def value(self) -> float | None:
        return self.numerator / self.denominator if self.denominator else None

    @property
    def interval(self) -> tuple[float, float] | None:
        return wilson(self.numerator, self.denominator)

    def to_dict(self) -> dict[str, Any]:
        return {
            "n": self.numerator,
            "of": self.denominator,
            "rate": self.value,
            "ci95": list(self.interval) if self.interval else None,
        }


@dataclass(frozen=True)
class ItemOutcome:
    """One item, one system, one trial. `category` is the gold category."""

    item_id: str
    category: str
    outcome: Outcome
    cost_usd: float
    latency_ms: float


def summarise(outcomes: list[ItemOutcome]) -> dict[str, Any]:
    """Every metric ADR-006 lists, over the finished (non-pending) outcomes.

    - in_schema item: correct (rows match gold), wrong (rows differ), refused, or error
      (the SQL failed to run).
    - refusal item (out_of_schema or should_refuse): refused is right; anything that
      returns rows is wrong.
    - "answered" means the system returned rows.
    """
    done = [o for o in outcomes if o.outcome != "pending"]
    ins = [o for o in done if o.category == "in_schema"]
    refusal_items = [o for o in done if o.category != "in_schema"]
    attempted = [o for o in ins if o.outcome != "refused"]
    correct = sum(o.outcome == "correct" for o in ins)
    answered = [o for o in done if o.outcome in ("correct", "wrong")]
    wrong_answered = sum(o.outcome == "wrong" for o in answered)
    latencies = [o.latency_ms for o in done]
    return {
        "items": len(done),
        "pending": len(outcomes) - len(done),
        "coverage": Rate(len(attempted), len(ins)).to_dict(),
        "execution_accuracy": Rate(correct, len(ins)).to_dict(),
        "accuracy_given_attempted": Rate(correct, len(attempted)).to_dict(),
        "false_refusal_rate": Rate(len(ins) - len(attempted), len(ins)).to_dict(),
        "wrong_answer_rate_given_answered": Rate(wrong_answered, len(answered)).to_dict(),
        "refusal_recall": Rate(
            sum(o.outcome == "refused" for o in refusal_items), len(refusal_items)
        ).to_dict(),
        "execution_error_rate": Rate(sum(o.outcome == "error" for o in done), len(done)).to_dict(),
        "mean_cost_usd": statistics.fmean(o.cost_usd for o in done) if done else None,
        "p50_latency_ms": statistics.median(latencies) if latencies else None,
    }


def _right_by_question(records: list[dict[str, Any]]) -> dict[str, bool]:
    """Each in-schema question, right when right in more than half of its trials."""
    trials: dict[str, list[str]] = {}
    for record in records:
        if record["category"] == "in_schema" and record["outcome"] != "pending":
            trials.setdefault(record["item_id"], []).append(record["outcome"])
    return {item: 2 * outs.count("correct") > len(outs) for item, outs in trials.items()}


def question_level(records: list[dict[str, Any]]) -> tuple[int, int]:
    """(questions right in most of their trials, distinct questions), in-schema only."""
    right = _right_by_question(records)
    return sum(right.values()), len(right)


def mcnemar_exact(only_after: int, only_before: int) -> float:
    """Two-sided exact McNemar p-value: a binomial test on the discordant questions."""
    n = only_after + only_before
    if n == 0:
        return 1.0
    tail = sum(math.comb(n, k) for k in range(min(only_after, only_before) + 1))
    return min(1.0, 2 * tail / 2**n)
