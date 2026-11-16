"""The before/after CLI rebuilds two runs from their checkpoints and pairs them."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from askwell.bench import paired


def _record(item: str, trial: int, outcome: str) -> dict[str, Any]:
    return {
        "key": f"fieldservice|m|t{trial}|ledgerline|{item}|v|x|y",
        "schema_id": "fieldservice",
        "model": "m",
        "trial": trial,
        "system": "ledgerline",
        "item_id": item,
        "gold": "fieldservice.jsonl",
        "category": "in_schema",
        "difficulty": "easy",
        "outcome": outcome,
        "cost_usd": 0.01,
        "latency_ms": 1.0,
        "error": None,
        "sql": None,
        "detail": {},
        "provenance": None,
    }


PLANNED = ["fs-001", "fs-002"]


def _key(item: str, trial: int) -> str:
    return f"fieldservice|m|t{trial}|ledgerline|{item}|v|x|y"


def _write_run(
    runs: Path,
    run_id: str,
    outcomes: dict[str, list[str]],
    planned: list[str] = PLANNED,
    trials: int = 3,
) -> None:
    run_dir = runs / run_id
    run_dir.mkdir(parents=True)
    config = {
        "schemas": ["fieldservice"],
        "systems": ["ledgerline"],
        "models": ["m"],
        "trials": 3,
        "gold": None,
        "planned_trials": {"fieldservice": trials},
        "planned_items": {"fieldservice": planned},
        "task_keys": [_key(item, t) for item in planned for t in range(1, trials + 1)],
    }
    (run_dir / "config.json").write_text(json.dumps(config))
    lines = [
        json.dumps({"key": _key(item, trial), "cost_usd": 0.01, "record": _record(item, trial, o)})
        for item, trials in outcomes.items()
        for trial, o in enumerate(trials, start=1)
    ]
    (run_dir / "results.jsonl").write_text("\n".join(lines) + "\n")


def test_two_runs_pair_with_planned_questions(tmp_path: Path) -> None:
    _write_run(tmp_path, "before", {"fs-001": ["wrong"] * 3})
    _write_run(
        tmp_path, "after", {"fs-001": ["correct", "correct", "wrong"], "fs-002": ["correct"] * 3}
    )
    before = paired.load_run("before", tmp_path)
    after = paired.load_run("after", tmp_path)
    assert before.spent_usd == pytest.approx(0.03)
    data = paired.compare(before, after)
    [row] = data["pairs"]
    # fs-002 never ran before, so it counts as not right there.
    assert (row["questions"], row["before_right"], row["after_right"]) == (2, 0, 2)
    assert (row["only_after"], row["only_before"]) == (2, 0)
    assert row["wrong_before"]["pooled"]["n"] == 3
    assert row["wrong_after"]["per_trial"][3]["n"] == 1
    text = paired.render(data)
    assert "| fieldservice | ledgerline | 2 | 0 | 2 | 2 | 0 |" in text


def test_a_run_of_named_items_keeps_its_planned_trials_and_items(tmp_path: Path) -> None:
    _write_run(tmp_path, "r", {"fs-002": ["correct", "wrong"]}, planned=["fs-002"], trials=2)
    result = paired.load_run("r", tmp_path)
    assert result.planned_trials == {"fieldservice": 2}
    assert result.planned_items == {"fieldservice": ["fs-002"]}


def test_checkpoint_entries_outside_the_runs_tasks_are_left_out(tmp_path: Path) -> None:
    _write_run(tmp_path, "r", {"fs-001": ["correct"]}, trials=1)
    stale = {"key": "fs-001|old-prompt", "cost_usd": 0.5, "record": _record("fs-001", 1, "wrong")}
    with (tmp_path / "r" / "results.jsonl").open("a") as f:
        f.write(json.dumps(stale) + "\n")
    result = paired.load_run("r", tmp_path)
    assert [r["outcome"] for r in result.records] == ["correct"]
    assert result.spent_usd == pytest.approx(0.01)


def test_a_run_without_its_recorded_plan_is_refused(tmp_path: Path) -> None:
    _write_run(tmp_path, "r", {"fs-001": ["correct"]})
    config_path = tmp_path / "r" / "config.json"
    config = json.loads(config_path.read_text())
    del config["task_keys"]
    config_path.write_text(json.dumps(config))
    with pytest.raises(ValueError, match="replay"):
        paired.load_run("r", tmp_path)


def test_a_finished_run_keeps_its_hashes_and_outcome(tmp_path: Path) -> None:
    _write_run(tmp_path, "r", {"fs-001": ["correct"]}, planned=["fs-001", "fs-002"], trials=1)
    config_path = tmp_path / "r" / "config.json"
    config = json.loads(config_path.read_text())
    config["registry_hashes"] = {"fieldservice": "abc"}
    config_path.write_text(json.dumps(config))
    outcome = {
        "aborted": True,
        "abort_reason": "budget",
        "deferred": {"fieldservice/ledgerline": 1},
        "csv_load_failures": {"fieldservice": {"parts": ["no_id_column"]}},
    }
    (tmp_path / "r" / "outcome.json").write_text(json.dumps(outcome))
    result = paired.load_run("r", tmp_path)
    assert result.registry_hashes == {"fieldservice": "abc"}
    assert (result.aborted, result.abort_reason) == (True, "budget")
    assert result.deferred == {"fieldservice/ledgerline": 1}
    assert result.csv_load_failures == {"fieldservice": {"parts": ["no_id_column"]}}


def test_without_an_outcome_file_the_tasks_with_no_entry_count_as_deferred(
    tmp_path: Path,
) -> None:
    _write_run(tmp_path, "done", {"fs-001": ["correct"], "fs-002": ["wrong"]}, trials=1)
    result = paired.load_run("done", tmp_path)
    assert (result.aborted, result.abort_reason, result.deferred) == (False, None, {})
    _write_run(tmp_path, "part", {"fs-001": ["correct"]}, trials=1)
    assert paired.load_run("part", tmp_path).deferred == {"fieldservice/ledgerline": 1}
