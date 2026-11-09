"""The eval report: a metrics table with 95% intervals, every Ledgerline miss with its
triage tag, and every question where a baseline beat Ledgerline.

Spider items are cited by ID only (e.g. `spider:123`, the index in dev.json); their
text is never written. A run with simulated model answers says so at the top.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

import yaml

from ledgerline.bench.items import ROOT
from ledgerline.bench.metrics import ItemOutcome, summarise
from ledgerline.bench.run import RunResult

REPORTS_DIR = ROOT / "evals" / "reports"
TRIAGE_DIR = ROOT / "evals" / "triage"
TRIAGE_TAGS = ("grammar_gap", "misread", "validator_false_reject", "builder_bug", "gold_issue")


def load_triage(schema_id: str) -> dict[str, dict[str, str]]:
    """`evals/triage/<schema>.yaml`: item id -> {tag, note}, written after a run."""
    path = TRIAGE_DIR / f"{schema_id}.yaml"
    if not path.exists():
        return {}
    data: dict[str, dict[str, str]] = yaml.safe_load(path.read_text()) or {}
    for item_id, entry in data.items():
        if entry.get("tag") not in TRIAGE_TAGS:
            raise ValueError(f"{path.name}: {item_id} has tag {entry.get('tag')!r}")
    return data


def simulation_note(records: list[dict[str, Any]]) -> str | None:
    pairs = sorted(
        {
            (r["provenance"]["simulated_by"], r["provenance"]["standing_in_for"])
            for r in records
            if r.get("provenance")
        }
    )
    if not pairs:
        return None
    described = "; ".join(f"simulated by {by}, standing in for {target}" for by, target in pairs)
    return f"Model responses {described}. This is not an OpenRouter measurement."


def build(result: RunResult) -> dict[str, Any]:
    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for record in result.records:
        groups[(record["schema_id"], record["system"], record["model"])].append(record)
    table = []
    for (schema_id, system, model), records in sorted(groups.items()):
        outcomes = [
            ItemOutcome(r["item_id"], r["category"], r["outcome"], r["cost_usd"], r["latency_ms"])
            for r in records
        ]
        trials = sorted({r["trial"] for r in records})
        table.append(
            {
                "schema": schema_id,
                "system": system,
                "model": model,
                "trials": len(trials),
                **summarise(outcomes),
            }
        )

    misses = []
    for record in result.records:
        if record["system"] != "ledgerline" or record["outcome"] == "correct":
            continue
        if record["category"] != "in_schema" and record["outcome"] == "refused":
            continue
        triage = load_triage(record["schema_id"]).get(record["item_id"], {})
        misses.append(
            {
                "schema": record["schema_id"],
                "item_id": record["item_id"],
                "trial": record["trial"],
                "model": record["model"],
                "outcome": record["outcome"],
                "issue_codes": record["detail"].get("issue_codes", []),
                "refusal": record["detail"].get("refusal"),
                "error": record["error"],
                "tag": triage.get("tag", "untriaged"),
                "note": triage.get("note", ""),
            }
        )

    by_item: dict[tuple[str, str, int, str], dict[str, str]] = defaultdict(dict)
    for record in result.records:
        key = (record["schema_id"], record["model"], record["trial"], record["item_id"])
        by_item[key][record["system"]] = record["outcome"]
    wins = [
        {"schema": s, "model": m, "trial": t, "item_id": i, "system": system}
        for (s, m, t, i), outcomes in sorted(by_item.items())
        for system, outcome in sorted(outcomes.items())
        if system != "ledgerline"
        and outcome == "correct"
        and outcomes.get("ledgerline") not in (None, "correct")
    ]
    return {
        "run_id": result.run_id,
        "simulation": simulation_note(result.records),
        "status": "aborted at budget"
        if result.aborted
        else ("partial" if result.deferred else "complete"),
        "abort_reason": result.abort_reason,
        "deferred": dict(result.deferred),
        "spent_usd": result.spent_usd,
        "registry_hashes": result.registry_hashes,
        "table": table,
        "misses": misses,
        "baseline_wins": wins,
    }


def _pct(rate: dict[str, Any]) -> str:
    if rate["rate"] is None:
        return "n/a"
    low, high = rate["ci95"]
    return (
        f"{rate['rate'] * 100:.1f}% [{low * 100:.0f}-{high * 100:.0f}] ({rate['n']}/{rate['of']})"
    )


def render_markdown(report: dict[str, Any]) -> str:
    lines = [f"# Eval report `{report['run_id']}`", ""]
    if report["simulation"]:
        lines += [f"> **{report['simulation']}**", ""]
    lines += [
        f"Status: {report['status']}. Spend: ${report['spent_usd']:.4f}.",
        "Rates show the value, the Wilson 95% interval, and the counts. Trials are pooled.",
        "",
        "| Schema | System | Model | Trials | Coverage | Exec. accuracy | Acc. given attempted "
        "| False refusals | Wrong given answered | Refusal recall | Exec. errors |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for row in report["table"]:
        lines.append(
            f"| {row['schema']} | {row['system']} | {row['model']} | {row['trials']} "
            f"| {_pct(row['coverage'])} | {_pct(row['execution_accuracy'])} "
            f"| {_pct(row['accuracy_given_attempted'])} | {_pct(row['false_refusal_rate'])} "
            f"| {_pct(row['wrong_answer_rate_given_answered'])} | {_pct(row['refusal_recall'])} "
            f"| {_pct(row['execution_error_rate'])} |"
        )
    lines += ["", "## Ledgerline misses", ""]
    if not report["misses"]:
        lines.append("None.")
    for miss in report["misses"]:
        why = miss["refusal"] or miss["error"] or ", ".join(miss["issue_codes"]) or "rows differ"
        lines.append(
            f"- `{miss['item_id']}` ({miss['schema']}, trial {miss['trial']}): {miss['outcome']}"
            f" — {why}. Tag: **{miss['tag']}**{'. ' + miss['note'] if miss['note'] else ''}"
        )
    lines += ["", "## Where a baseline beat Ledgerline", ""]
    if not report["baseline_wins"]:
        lines.append("None.")
    for win in report["baseline_wins"]:
        lines.append(
            f"- `{win['item_id']}` ({win['schema']}, trial {win['trial']}): {win['system']}"
        )
    if report["registry_hashes"]:
        lines += ["", "## Spider registries (generated by `registry init`, unedited, draft)", ""]
        for schema, digest in sorted(report["registry_hashes"].items()):
            lines.append(f"- {schema}: `{digest}`")
    return "\n".join(lines) + "\n"


def write(report: dict[str, Any], out_dir: Path = REPORTS_DIR) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    md = out_dir / f"{report['run_id']}.md"
    js = out_dir / f"{report['run_id']}.json"
    md.write_text(render_markdown(report), encoding="utf-8")
    js.write_text(
        json.dumps(report, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8"
    )
    return md, js
