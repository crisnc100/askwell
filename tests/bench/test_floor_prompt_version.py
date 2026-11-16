"""A floor's written note describes one prompt version's results. A run made with another
prompt version keeps the computed verdict but gets a note naming its own version, never
another release's explanation."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from askwell.bench.report import build, floor_checks, render_markdown
from askwell.bench.run import RunResult

FLOORS = """\
fieldservice:
  prompt_version: interpret-v2
  floors:
    execution_accuracy: {min: 0.80}
  status_note: in v0.2 on the seen questions
  cause: v0.2 numbers
  next: v0.2 plan
"""


def _row() -> dict[str, Any]:
    return {
        "schema": "fieldservice",
        "system": "ledgerline",
        "execution_accuracy": {"n": 9, "of": 10, "rate": 0.9, "ci95": [0.6, 1.0]},
    }


def _floors(tmp_path: Path, versions: dict[str, list[str]] | None) -> dict[str, Any]:
    path = tmp_path / "floors.yaml"
    path.write_text(FLOORS)
    [floor] = floor_checks([_row()], path, prompt_versions=versions)
    return floor


def test_the_written_note_applies_to_its_own_prompt_version(tmp_path: Path) -> None:
    floor = _floors(tmp_path, {"fieldservice": ["interpret-v2"]})
    assert floor["met"]
    assert (floor["status_note"], floor["cause"], floor["next"]) == (
        "in v0.2 on the seen questions",
        "v0.2 numbers",
        "v0.2 plan",
    )


def test_another_prompt_version_gets_a_note_naming_it(tmp_path: Path) -> None:
    floor = _floors(tmp_path, {"fieldservice": ["interpret-v3"]})
    assert floor["met"]
    assert floor["status_note"] == "with prompt interpret-v3"
    assert floor["cause"] is None
    assert floor["next"] is None
    assert "v0.2" not in str(floor)


def test_a_run_mixing_prompt_versions_names_them_all(tmp_path: Path) -> None:
    floor = _floors(tmp_path, {"fieldservice": ["interpret-v2", "interpret-v3"]})
    assert floor["status_note"] == "with prompts interpret-v2, interpret-v3"
    assert floor["cause"] is None


def test_the_report_reads_the_version_from_the_records() -> None:
    record = {
        "key": "fieldservice|m|t1|ledgerline|fs-001|interpret-v3|abc|def",
        "schema_id": "fieldservice",
        "model": "anthropic:claude-haiku-5-5",
        "trial": 1,
        "system": "ledgerline",
        "item_id": "fs-001",
        "gold": "fieldservice.jsonl",
        "category": "in_schema",
        "difficulty": "easy",
        "outcome": "correct",
        "cost_usd": 0.0,
        "latency_ms": 1.0,
        "error": None,
        "sql": None,
        "detail": {},
        "provenance": None,
    }
    result = RunResult(run_id="r", records=[record], systems=["ledgerline"], models=["m"])
    report = build(result)
    [floor] = report["floors"]
    assert floor["status_note"] == "with prompt interpret-v3"
    assert "in v0.2" not in render_markdown(report)
