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
from ledgerline.config import get_settings

REPORTS_DIR = ROOT / "evals" / "reports"
TRIAGE_DIR = ROOT / "evals" / "triage"
FLOORS_FILE = ROOT / "evals" / "floors.yaml"
METRIC_LABELS = {
    "execution_accuracy": "Execution accuracy",
    "wrong_answer_rate_given_answered": "Wrong answers among answered",
}
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


def floor_checks(
    table: list[dict[str, Any]], path: Path | None = None, default_model: str | None = None
) -> list[dict[str, Any]]:
    """Each schema's floors from `evals/floors.yaml`, checked on Ledgerline's row for the
    configured default model, never on whichever model sorts first. With
    no default model given, a schema is checked only if it has exactly one model row."""
    source = path or FLOORS_FILE
    if not source.exists():
        return []
    config: dict[str, Any] = yaml.safe_load(source.read_text()) or {}
    out: list[dict[str, Any]] = []
    for schema_id, entry in config.items():
        rows = [r for r in table if r["schema"] == schema_id and r["system"] == "ledgerline"]
        if default_model is not None:
            rows = [r for r in rows if r.get("model") == default_model]
        if len(rows) != 1:
            continue
        row = rows[0]
        checks = []
        for metric, bound in entry["floors"].items():
            value = row[metric]["rate"]
            if "min" in bound:
                ok = value is not None and value >= bound["min"]
                rule = f">= {bound['min'] * 100:.0f}%"
            else:
                ok = value is not None and value <= bound["max"]
                rule = f"<= {bound['max'] * 100:.0f}%"
            checks.append({"metric": metric, "rule": rule, "rate": row[metric], "met": ok})
        out.append(
            {
                "schema": schema_id,
                "model": row.get("model"),
                "met": all(c["met"] for c in checks),
                "checks": checks,
                "status_note": entry.get("status_note"),
                "cause": entry.get("cause"),
                "next": entry.get("next"),
            }
        )
    return out


def _is_spider(record: dict[str, Any]) -> bool:
    return str(record["schema_id"]).startswith("spider_")


def _public_refusal(record: dict[str, Any]) -> str | None:
    """Refusal text can quote data values ("name the breed: X, Y or Z"). For Spider
    items, whose data must never be committed, only the reason codes are kept."""
    refusal = record["detail"].get("refusal")
    if refusal is None or not _is_spider(record):
        return refusal
    codes = record["detail"].get("issue_codes") or []
    return f"refused ({', '.join(codes)})" if codes else "refused (unanswerable)"


def _public_error(record: dict[str, Any]) -> str | None:
    """Database errors can quote values too; Spider items keep only the fact."""
    error = record["error"]
    if error is None or not _is_spider(record):
        return error
    return "execution error"


def simulation_note(records: list[dict[str, Any]]) -> str | None:
    # Every attempt counts: a retry can come from a different source than the first
    # answer, and either alone may carry the simulation mark.
    marks: list[dict[str, str]] = []
    for r in records:
        if r.get("provenance"):
            marks.append(r["provenance"])
        marks += [p for p in (r.get("detail") or {}).get("attempt_provenance", []) if p]
    pairs = sorted({(m["simulated_by"], m["standing_in_for"]) for m in marks})
    if not pairs:
        return None
    described = "; ".join(f"simulated by {by}, standing in for {target}" for by, target in pairs)
    return f"Model responses {described}. This is not an OpenRouter measurement."


SQL_AGENT_NOT_RUN = (
    "sql_agent baseline not run: needs a live model (multi-step tool calls can't be "
    "honestly simulated in one pass)."
)


def run_notes(result: RunResult, simulated: bool) -> list[str]:
    """Plain statements of what this run did not measure, shown under the title."""
    notes: list[str] = []
    if "sql_agent" not in result.systems:
        notes.append(SQL_AGENT_NOT_RUN)
    if simulated and len(result.models) == 1:
        notes.append(
            f"One target model ({result.models[0]}). A second model runs once there is an "
            "OpenRouter key: simulating a second vendor with the same stand-in would add "
            "no real diversity."
        )
    if simulated and result.trials == 1:
        notes.append(
            "Trials: 1. Repeating trials with the same stand-in would measure the "
            "stand-in's variance, not the target model's."
        )
    return notes


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
                "refusal": _public_refusal(record),
                "error": _public_error(record),
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
    simulation = simulation_note(result.records)
    return {
        "run_id": result.run_id,
        "simulation": simulation,
        "notes": run_notes(result, simulation is not None),
        "trials": result.trials,
        "status": "aborted at budget"
        if result.aborted
        else ("partial" if result.deferred else "complete"),
        "abort_reason": result.abort_reason,
        "deferred": dict(result.deferred),
        "spent_usd": result.spent_usd,
        "registry_hashes": result.registry_hashes,
        "table": table,
        "floors": floor_checks(table, default_model=get_settings().default_model),
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
    lines: list[str] = []
    if report["simulation"]:
        # First line on purpose: nobody should read a number before knowing it is simulated.
        lines += [f"> **{report['simulation']}**", ""]
    lines += [f"# Eval report `{report['run_id']}`", ""]
    for note in report["notes"]:
        lines.append(f"- {note}")
    if report["notes"]:
        lines.append("")
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
    for floor in report.get("floors", []):
        verdict = "met" if floor["met"] else "not met"
        lines += [
            "",
            f"## Floor check: {floor['schema']}, {floor['model']} (v0.1 acceptance floor)",
            "",
        ]
        for check in floor["checks"]:
            mark = "met" if check["met"] else "NOT met"
            label = METRIC_LABELS.get(check["metric"], check["metric"])
            lines.append(f"- {label} {check['rule']}: {_pct(check['rate'])}, {mark}")
        lines.append("")
        note = f" {floor['status_note']}" if floor["status_note"] else ""
        lines.append(f"Result: **{verdict}**{note}.")
        if floor["cause"]:
            lines.append(f"Why: {floor['cause']}")
        if floor["next"]:
            lines.append(f"Next: {floor['next']}")
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
