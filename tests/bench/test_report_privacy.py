"""Spider data never reaches committed files: refusal text is replaced by its reason code
for Spider items, and committed reports, triage notes, docs and the build folder contain
no value from a Spider categorical column (checked against a committed hash list, so CI
needs no data)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from ledgerline.bench import report as report_module
from ledgerline.bench.privacy import ngrams
from ledgerline.bench.run import RunResult

ROOT = Path(__file__).resolve().parents[2]
HASHES = ROOT / "evals" / "spider_forbidden_values.json"
MAX_WORDS = int(json.loads(HASHES.read_text())["max_words"])
THIS_FILE = Path(__file__).resolve()
SCANNED = [
    *sorted((ROOT / "evals" / "reports").glob("*.md")),
    *sorted((ROOT / "evals" / "reports").glob("*.json")),
    *sorted((ROOT / "evals" / "triage").glob("*.yaml")),
    *sorted((ROOT / "evals" / "gold").glob("*.md")),
    ROOT / "evals" / "floors.yaml",
    ROOT / "README.md",
    *sorted((ROOT / "docs").rglob("*.md")),
    *sorted(p for p in (ROOT / "builds").rglob("*") if p.is_file()),
    # This file is the scanner's own fixture: it must spell out probe values.
    *sorted(p for p in (ROOT / "tests").rglob("*.py") if p.resolve() != THIS_FILE),
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


# Exact prose phrases that contain a word which is also a Spider value, allowed only in
# the files listed. The bare word is still caught everywhere else.
ALLOWED_PHRASES: dict[str, tuple[str, ...]] = {
    "docs/adr/ADR-005-replay-and-budget.md": ("a hard per-run budget", "the run stops hard"),
    "docs/adr/README.md": ("a hard per-run budget",),
    "docs/rerecord.md": ("is a hard cap",),
    # builds/: the plan, prompts and archived grades use "hard" as a difficulty level or a
    # budget word.
    "builds/v01/context.md": ("a hard per-run budget",),
    "builds/v01/bounce-prompt.md": ("a hard per-run budget",),
    "builds/v01/bounce-p5-prompt.md": (
        "a hard per-run budget",
        "easy|medium|hard",
        "a hard stop at",
        "≥10 hard",
    ),
    "builds/v01/plan.md": ("easy|medium|hard", "a hard stop at", "≥10 hard"),
    "builds/v01/grade-pr1-prompt.md": (">=10 hard",),
    "builds/v01/grade-pr1.json": (">=10 hard", "including 12 hard"),
    "builds/v01/recheck-pr1-prompt.md": (">=10 hard",),
    "builds/v01/recheck-pr1.json": (">=10 hard", "including 12 hard"),
    "builds/v01/log.md": (
        "one shared hard budget",
        "12 hard",
        "174 hard",
        "one hard budget",
    ),
    "builds/v01/testchange-prompt.md": ("suppress_health_check",),
    # tests/: "hard" is Spider's hardness level and a budget word; Hypothesis's API name
    # contains "health check".
    "tests/test_gold.py": ('difficulty["hard"]',),
    "tests/test_llm_budget.py": ("abort at the hard stop",),
    "tests/test_spider_selection.py": ('"hard"', "174 hard", "test_hardness_hard"),
    "tests/core/test_sqlbuild.py": ("suppress_health_check",),
}


def scan(relative: str, text: str, forbidden: set[str]) -> list[str]:
    """Every phrase in `text` that normalises to a forbidden value. Text and values go
    through the same `normalise`, so quotes, backticks and brackets never hide a value."""
    for phrase in ALLOWED_PHRASES.get(relative, ()):
        text = text.replace(phrase, " ")
    return [
        f"{relative}: {gram!r}"
        for gram in sorted(ngrams(text, MAX_WORDS))
        if hashlib.sha256(gram.encode()).hexdigest() in forbidden
    ]


def _forbidden() -> set[str]:
    forbidden = set(json.loads(HASHES.read_text())["sha256"])
    assert forbidden
    return forbidden


def test_committed_files_hold_no_spider_categorical_values() -> None:
    forbidden = _forbidden()
    hits: list[str] = []
    for path in SCANNED:
        hits += scan(str(path.relative_to(ROOT)), path.read_text(encoding="utf-8"), forbidden)
    assert hits == []


def test_a_bare_value_is_caught_even_where_a_phrase_is_allowed() -> None:
    forbidden = _forbidden()
    assert scan("evals/reports/x.md", "- spider:1: surface hard", forbidden)
    assert scan("docs/rerecord.md", "the surface was hard", forbidden)
    assert scan("docs/rerecord.md", "`--budget` is a hard cap", forbidden) == []


def test_a_spider_value_in_a_builds_file_fails_the_scan() -> None:
    forbidden = _forbidden()
    assert scan("builds/v01/grade-pr9.json", '"evidence": "value hard"', forbidden)
    assert scan("builds/v01/plan.md", "the court surface is hard", forbidden)
    assert any("builds" in str(path) for path in SCANNED)


def test_quoted_and_bracketed_values_are_caught() -> None:
    forbidden = _forbidden()
    for text in ("surface = 'hard'", 'surface = "hard"', "surface = `hard`", "surface (hard)"):
        assert scan("evals/triage/spider_wta_1.yaml", text, forbidden), text


def test_generator_and_scanner_normalise_alike() -> None:
    from ledgerline.bench.privacy import digest, normalise

    assert normalise("'Mercedes-Benz'") == "mercedes benz"
    assert normalise("  Daily   Accommodation ") == "daily accommodation"
    assert digest("`HARD`") == hashlib.sha256(b"hard").hexdigest()
    assert scan("x.md", "the (Hard) court", {digest("hard")})
