"""The report lists every Askwell system's misses, the CSV path's included, and gives each
miss the triage note written for its own run when one exists."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from askwell.bench import report as report_module
from askwell.bench.report_schema import Report
from askwell.bench.run import RunResult


def _record(system: str, item: str, outcome: str) -> dict[str, Any]:
    return {
        "key": f"spider_x|m|t1|{system}|{item}|interpret-v3|a|b",
        "schema_id": "spider_x",
        "model": "m",
        "trial": 1,
        "system": system,
        "item_id": item,
        "gold": None,
        "category": "in_schema",
        "difficulty": "easy",
        "outcome": outcome,
        "cost_usd": 0.0,
        "latency_ms": 1.0,
        "error": None,
        "sql": None,
        "detail": {},
        "provenance": None,
    }


@pytest.fixture
def triage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(report_module, "TRIAGE_DIR", tmp_path)
    (tmp_path / "spider_x.yaml").write_text(
        """\
spider:1:
  tag: validator_false_reject
  note: written for the first run
  runs:
    later:
      tag: gold_issue
      note: 'later: answered, and the gold compares text'
spider:2:
  runs:
    later:
      tag: misread
      note: 'later: wrong'
"""
    )
    return tmp_path


def _report(run_id: str, records: list[dict[str, Any]], systems: list[str]) -> dict[str, Any]:
    result = RunResult(run_id=run_id, records=records, systems=systems, models=["m"])
    report = report_module.build(result)
    Report.model_validate(json.loads(json.dumps(report, default=str)))
    return report


def test_the_csv_paths_misses_are_listed(triage: Path) -> None:
    report = _report(
        "csv",
        [
            _record("askwell_csv", "spider:1", "wrong"),
            _record("askwell_csv", "spider:3", "correct"),
        ],
        ["askwell_csv"],
    )
    [miss] = report["misses"]
    assert (miss["item_id"], miss["system"], miss["outcome"]) == (
        "spider:1",
        "askwell_csv",
        "wrong",
    )
    assert "`spider:1` (spider_x, " in report_module.render_markdown(report)
    assert "askwell_csv" in report_module.render_markdown(report).split("## Ledgerline misses")[1]


def test_a_baselines_misses_are_not_listed(triage: Path) -> None:
    report = _report("r", [_record("oneshot", "spider:1", "wrong")], ["oneshot"])
    assert report["misses"] == []


def test_a_note_written_for_the_run_wins(triage: Path) -> None:
    report = _report("later", [_record("ledgerline", "spider:1", "wrong")], ["ledgerline"])
    [miss] = report["misses"]
    assert (miss["tag"], miss["note"]) == (
        "gold_issue",
        "later: answered, and the gold compares text",
    )


def test_another_run_gets_the_general_note(triage: Path) -> None:
    report = _report("first", [_record("ledgerline", "spider:1", "refused")], ["ledgerline"])
    [miss] = report["misses"]
    assert (miss["tag"], miss["note"]) == ("validator_false_reject", "written for the first run")


def test_an_entry_only_for_other_runs_leaves_the_miss_untriaged(triage: Path) -> None:
    report = _report("first", [_record("ledgerline", "spider:2", "wrong")], ["ledgerline"])
    [miss] = report["misses"]
    assert (miss["tag"], miss["note"]) == ("untriaged", "")


def test_a_bad_tag_inside_runs_is_refused(triage: Path) -> None:
    (triage / "spider_x.yaml").write_text("spider:1:\n  runs:\n    r: {tag: nope, note: n}\n")
    with pytest.raises(ValueError, match="nope"):
        report_module.load_triage("spider_x")
