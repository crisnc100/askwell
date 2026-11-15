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
        "task_keys": [f"{item}|{t}" for item in planned for t in range(1, trials + 1)],
    }
    (run_dir / "config.json").write_text(json.dumps(config))
    lines = [
        json.dumps({"key": f"{item}|{trial}", "cost_usd": 0.01, "record": _record(item, trial, o)})
        for item, trials in outcomes.items()
        for trial, o in enumerate(trials, start=1)
    ]
    (run_dir / "results.jsonl").write_text("\n".join(lines) + "\n")


def test_two_runs_pair_with_planned_questions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(paired, "items_for", lambda _schema: _items(["fs-001", "fs-002"]))
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


def _items(ids: list[str]) -> list[Any]:
    from askwell.bench.items import EvalItem

    return [EvalItem(i, "fieldservice", "in_schema", "q", "SELECT 1", False, "easy") for i in ids]
