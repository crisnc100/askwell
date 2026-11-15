"""Before and after on the same questions, from two finished runs' checkpoints:

    uv run python -m askwell.bench.paired <before run id> <after run id> [--out <name>]

Per schema, gold, system and model present in both runs: the question-level pairing
(`report.compare_runs`, with its exact McNemar p-value) and each run's wrong answers
among answered, per trial and pooled. `--out` also writes evals/paired/<name>.md and
.json, apart from evals/reports/, whose files are all eval reports. It reads
evals/runs/<id>/ only and makes no model call.
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

from askwell.bench.items import ROOT
from askwell.bench.metrics import ItemOutcome, summarise
from askwell.bench.report import compare_runs
from askwell.bench.run import RUNS_DIR, RunResult, items_for, trials_for
from askwell.llm.budget import Checkpoint

PAIRED_DIR = ROOT / "evals" / "paired"


def load_run(run_id: str, runs_dir: Path = RUNS_DIR) -> RunResult:
    """A finished run rebuilt from its config and checkpoint, with the trials and
    in-schema items it planned, so unfinished trials count as not right."""
    run_dir = runs_dir / run_id
    config: dict[str, Any] = json.loads((run_dir / "config.json").read_text())
    entries, spent = Checkpoint(run_dir / "results.jsonl").load()
    gold = Path(config["gold"]) if config.get("gold") else None
    if gold is not None and not gold.is_absolute():
        gold = ROOT / gold
    schemas: list[str] = config["schemas"]
    trials = int(config["trials"])
    return RunResult(
        run_id=run_id,
        records=[entry["record"] for entry in entries.values()],
        spent_usd=spent,
        systems=list(config["systems"]),
        models=list(config["models"]),
        trials=trials,
        planned_trials={schema: trials_for(schema, trials) for schema in schemas},
        planned_items={
            schema: [
                item.id
                for item in (items_for(schema) if gold is None else items_for(schema, gold))
                if item.category == "in_schema"
            ]
            for schema in schemas
        },
    )


def wrong_given_answered(result: RunResult) -> dict[tuple[str, str, str, str], dict[str, Any]]:
    """Per schema, gold, system and model: wrong among answered for each trial and pooled."""
    groups: dict[tuple[str, str, str, str], dict[int, list[ItemOutcome]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for record in result.records:
        key = (
            record["schema_id"],
            str(record.get("gold") or ""),
            record["system"],
            record["model"],
        )
        groups[key][int(record["trial"])].append(
            ItemOutcome(
                record["item_id"],
                record["category"],
                record["outcome"],
                float(record["cost_usd"]),
                float(record["latency_ms"]),
            )
        )
    out: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for key, by_trial in groups.items():
        pooled = [o for outcomes in by_trial.values() for o in outcomes]
        out[key] = {
            "per_trial": {
                trial: summarise(outcomes)["wrong_answer_rate_given_answered"]
                for trial, outcomes in sorted(by_trial.items())
            },
            "pooled": summarise(pooled)["wrong_answer_rate_given_answered"],
        }
    return out


def compare(before: RunResult, after: RunResult) -> dict[str, Any]:
    old, new = wrong_given_answered(before), wrong_given_answered(after)
    rows = []
    for pair in compare_runs(before, after):
        key = (pair["schema"], pair["gold"], pair["system"], pair["model"])
        rows.append({**pair, "wrong_before": old.get(key), "wrong_after": new.get(key)})
    return {
        "before": before.run_id,
        "after": after.run_id,
        "spent_usd": {"before": before.spent_usd, "after": after.spent_usd},
        "pairs": rows,
    }


def _rate(rate: dict[str, Any] | None) -> str:
    if not rate or rate["rate"] is None:
        return "n/a"
    return f"{rate['rate'] * 100:.1f}% ({rate['n']}/{rate['of']})"


def render(data: dict[str, Any]) -> str:
    lines = [
        f"# Before and after: `{data['before']}` vs `{data['after']}`",
        "",
        "Question-level: right in more than half of the planned trials; an unfinished trial"
        " is not right. The p-value is the exact two-sided McNemar test on the questions"
        " where the two runs differ.",
        "",
        "| Schema | System | Questions | Right before | Right after | Only after | Only before"
        " | p | Wrong/answered before | Wrong/answered after |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for row in data["pairs"]:
        wrong_before = row["wrong_before"] or {}
        wrong_after = row["wrong_after"] or {}
        lines.append(
            f"| {row['schema']} | {row['system']} | {row['questions']} | {row['before_right']}"
            f" | {row['after_right']} | {row['only_after']} | {row['only_before']}"
            f" | {row['p_value']:.4f} | {_rate(wrong_before.get('pooled'))}"
            f" | {_rate(wrong_after.get('pooled'))} |"
        )
    lines += ["", "Wrong among answered, per trial:", ""]
    for row in data["pairs"]:
        for side in ("before", "after"):
            per_trial = (row[f"wrong_{side}"] or {}).get("per_trial", {})
            trials = ", ".join(f"t{t} {_rate(r)}" for t, r in per_trial.items())
            lines.append(f"- {row['schema']} {row['system']} {side}: {trials or 'n/a'}")
    return "\n".join(lines) + "\n"


def main(argv: list[str]) -> int:
    args = [a for a in argv if not a.startswith("--")]
    out = argv[argv.index("--out") + 1] if "--out" in argv else None
    if out is not None:
        args.remove(out)
    if len(args) != 2:
        print("usage: python -m askwell.bench.paired <before> <after> [--out <name>]")
        return 2
    data = compare(load_run(args[0]), load_run(args[1]))
    text = render(data)
    print(text, end="")
    if out is not None:
        PAIRED_DIR.mkdir(parents=True, exist_ok=True)
        (PAIRED_DIR / f"{out}.md").write_text(text, encoding="utf-8")
        (PAIRED_DIR / f"{out}.json").write_text(
            json.dumps(data, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
