"""Spider data never reaches committed files: refusal text is replaced by its reason code
for Spider items, and committed reports, triage notes and docs contain no value from a
Spider categorical column (checked against a committed hash list, so CI needs no data)."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from ledgerline.bench import report as report_module
from ledgerline.bench.run import RunResult

ROOT = Path(__file__).resolve().parents[2]
HASHES = ROOT / "evals" / "spider_forbidden_values.json"
SCANNED = [
    *sorted((ROOT / "evals" / "reports").glob("*.md")),
    *sorted((ROOT / "evals" / "reports").glob("*.json")),
    *sorted((ROOT / "evals" / "triage").glob("*.yaml")),
    *sorted((ROOT / "docs").rglob("*.md")),
]


def _record(schema: str, refusal: str | None, error: str | None = None) -> dict[str, object]:
    return {
        "schema_id": schema,
        "system": "ledgerline",
        "model": "m",
        "trial": 1,
        "item_id": "spider:1" if schema.startswith("spider_") else "fs-001",
        "category": "in_schema",
        "outcome": "refused" if refusal else "error",
        "cost_usd": 0.0,
        "latency_ms": 1.0,
        "error": error,
        "sql": None,
        "detail": {"refusal": refusal, "issue_codes": ["ambiguous_path"]},
        "provenance": None,
    }


def test_spider_refusal_and_error_text_is_replaced_by_reason_codes() -> None:
    result = RunResult(
        run_id="t",
        records=[
            _record("spider_dog_kennels", "Name the breed (SECRETVALUE) and I can answer."),
            _record("spider_dog_kennels", None, error="no such value SECRETVALUE"),
            _record("fieldservice", "No marketing data."),
        ],
        systems=["ledgerline"],
        models=["m"],
    )
    report = report_module.build(result)
    text = json.dumps(report) + report_module.render_markdown(report)
    assert "SECRETVALUE" not in text
    spider = [m for m in report["misses"] if m["schema"].startswith("spider_")]
    assert spider[0]["refusal"] == "refused (ambiguous_path)"
    assert spider[1]["error"] == "execution error"
    assert next(m for m in report["misses"] if m["schema"] == "fieldservice")["refusal"] == (
        "No marketing data."
    )


def _ngrams(text: str, longest: int = 4) -> set[str]:
    words = re.findall(r"[\w'-]+", text.lower())
    grams: set[str] = set()
    for n in range(1, longest + 1):
        for i in range(len(words) - n + 1):
            grams.add(" ".join(words[i : i + n]))
    return grams


def test_committed_files_hold_no_spider_categorical_values() -> None:
    forbidden = set(json.loads(HASHES.read_text())["sha256"])
    assert forbidden
    hits = []
    for path in SCANNED:
        for gram in _ngrams(path.read_text(encoding="utf-8")):
            if hashlib.sha256(gram.encode()).hexdigest() in forbidden:
                hits.append(f"{path.relative_to(ROOT)}: {gram!r}")
    assert hits == []
