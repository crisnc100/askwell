"""Apply ADR-004's selection rule (Amendment 1) to a finished fieldservice eval run.

    uv run python -m scripts.select_model <run id>

It reads `evals/runs/<run id>/results.jsonl`, scores the `ledgerline` system for each
model, and writes `evals/reports/model-selection-<run id>.md`. It makes no model calls.
"""

from __future__ import annotations

import json
import statistics
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ledgerline.bench import report as report_module
from ledgerline.bench import run as run_module
from ledgerline.llm.providers import ANTHROPIC_PREFIX

MAX_UNREADABLE = 0.02
MIN_REFUSAL_RECALL = 23
MAX_P50_MS = 3000.0
CLEARLY_WORSE = 4


@dataclass(frozen=True)
class Candidate:
    model: str
    questions: int
    cost_per_question: float
    correct: int
    answerable: int
    wrong: int
    refusals_caught: int
    refusal_items: int
    calls: int
    unreadable: int
    p50_ms: float

    @property
    def unreadable_rate(self) -> float:
        return self.unreadable / self.calls if self.calls else 0.0

    def gate_failures(self) -> list[str]:
        failed: list[str] = []
        if self.unreadable_rate > MAX_UNREADABLE:
            failed.append("unreadable")
        if self.refusals_caught < MIN_REFUSAL_RECALL:
            failed.append("refusal recall")
        if self.p50_ms > MAX_P50_MS:
            failed.append("latency")
        return failed


def candidates(records: list[dict[str, Any]]) -> list[Candidate]:
    by_model: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        if record["system"] == "ledgerline":
            by_model.setdefault(record["model"], []).append(record)
    out: list[Candidate] = []
    for model, rows in by_model.items():
        answerable = [r for r in rows if r["category"] == "in_schema"]
        refusal_items = [r for r in rows if r["category"] != "in_schema"]
        out.append(
            Candidate(
                model=model,
                questions=len(rows),
                cost_per_question=statistics.fmean(r["cost_usd"] for r in rows),
                correct=sum(r["outcome"] == "correct" for r in answerable),
                answerable=len(answerable),
                wrong=sum(r["outcome"] == "wrong" for r in rows),
                refusals_caught=sum(r["outcome"] == "refused" for r in refusal_items),
                refusal_items=len(refusal_items),
                calls=sum(int(r["detail"].get("attempts", 0)) for r in rows),
                unreadable=sum(int(r["detail"].get("parse_errors", 0)) for r in rows),
                p50_ms=statistics.median(r["latency_ms"] for r in rows),
            )
        )
    return sorted(out, key=lambda c: c.cost_per_question)


@dataclass(frozen=True)
class Choice:
    default: Candidate
    second: Candidate | None
    eligible: list[Candidate]
    best: Candidate
    note: str


def _vendor(model: str) -> str:
    """The model's maker, whichever provider serves it: `anthropic:<id>` (the Anthropic
    API) and `anthropic/<id>` (OpenRouter) are the same vendor."""
    if model.startswith(ANTHROPIC_PREFIX):
        return "anthropic"
    return model.split("/", 1)[0]


def choose(found: list[Candidate]) -> Choice:
    """The rule, step by step: gates, then the cheapest that is not clearly worse."""
    eligible = [c for c in found if not c.gate_failures()]
    pool = eligible or found
    best = max(pool, key=lambda c: (c.correct, -c.wrong, -c.cost_per_question))
    close = [
        c
        for c in pool
        if best.correct - c.correct < CLEARLY_WORSE and c.wrong - best.wrong < CLEARLY_WORSE
    ]
    # ADR-004 step 7: when nothing passes the gates, the best model ships, not the
    # cheapest one near it.
    default = min(close, key=lambda c: c.cost_per_question) if eligible else best
    ties = [c for c in close if c.cost_per_question == default.cost_per_question]
    note = "" if eligible else "No candidate passed every gate; this is the best one."
    if len(ties) > 1:
        note += " Tied on cost: the live Spider run decides (ADR-004, rule step 5)."
    others = [c for c in pool if _vendor(c.model) != _vendor(default.model)]
    second = max(others, key=lambda c: (c.correct, -c.wrong)) if others else None
    return Choice(default, second, eligible, best, note.strip())


def render(run_id: str, found: list[Candidate], choice: Choice) -> str:
    lines = [
        f"# Model selection: {run_id}",
        "",
        "ADR-004's rule (Amendment 1), applied to one live fieldservice pass of the "
        "`ledgerline` system. Costs are measured, not list prices.",
        "",
        "| Model | Cost per question (USD) | Correct | Wrong | Refusal recall | "
        "Unreadable | p50 latency | Gates failed |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for c in found:
        lines.append(
            f"| `{c.model}` | {c.cost_per_question:.6f} | {c.correct}/{c.answerable} | "
            f"{c.wrong} | {c.refusals_caught}/{c.refusal_items} | "
            f"{c.unreadable}/{c.calls} ({c.unreadable_rate:.1%}) | {c.p50_ms / 1000:.2f} s | "
            f"{', '.join(c.gate_failures()) or 'none'} |"
        )
    lines += [
        "",
        f"- **Best eligible:** `{choice.best.model}` ({choice.best.correct} correct).",
        f"- **Default:** `{choice.default.model}`.",
        f"- **Second:** `{choice.second.model}`." if choice.second else "- **Second:** none.",
    ]
    if choice.note:
        lines.append(f"- **Note:** {choice.note}")
    return "\n".join(lines) + "\n"


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print(__doc__)
        return 2
    run_id = argv[0]
    path: Path = run_module.RUNS_DIR / run_id / "results.jsonl"
    records = [
        json.loads(line)["record"]
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and json.loads(line)["record"] is not None
    ]
    records = [r for r in records if r["schema_id"] == "fieldservice"]
    found = candidates(records)
    out = report_module.REPORTS_DIR / f"model-selection-{run_id}.md"
    out.write_text(render(run_id, found, choose(found)), encoding="utf-8")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
