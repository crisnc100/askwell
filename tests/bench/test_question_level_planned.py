"""Question-level accuracy counts against the trials planned, not the trials that
finished: a missing trial is not right, so an unfinished run never lowers the bar."""

from __future__ import annotations

from typing import Any

from askwell.bench.metrics import question_level
from askwell.bench.report import build, compare_runs
from askwell.bench.run import RunResult


def _record(item: str, trial: int, outcome: str, schema: str = "fieldservice") -> dict[str, Any]:
    return {
        "key": f"ledgerline|{item}|{trial}",
        "schema_id": schema,
        "model": "m",
        "trial": trial,
        "system": "ledgerline",
        "item_id": item,
        "gold": "holdout-v03.jsonl" if schema == "fieldservice" else "spider_ids.json",
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


def test_one_right_trial_of_three_planned_is_not_right() -> None:
    records = [
        _record("q1", 1, "correct"),
        _record("q2", 1, "correct"),
        _record("q2", 2, "correct"),
    ]
    assert question_level(records, planned=3) == (1, 2)


def test_a_pending_trial_counts_as_not_right() -> None:
    records = [
        _record("q1", 1, "correct"),
        _record("q1", 2, "pending"),
        _record("q1", 3, "wrong"),
    ]
    assert question_level(records, planned=3) == (0, 1)


def test_the_report_uses_the_planned_trials_per_schema() -> None:
    result = RunResult(
        run_id="r",
        records=[
            _record("q1", 1, "correct"),
            _record("spider:1", 1, "correct", schema="spider_car_1"),
        ],
        systems=["ledgerline"],
        models=["m"],
        trials=3,
    )
    rows = {row["schema"]: row["right"] for row in build(result)["question_level"]}
    assert (rows["fieldservice"]["n"], rows["fieldservice"]["of"]) == (0, 1)
    # Spider runs one trial (ADR-006), so one right trial is a right question.
    assert (rows["spider_car_1"]["n"], rows["spider_car_1"]["of"]) == (1, 1)


def test_compare_runs_counts_missing_trials_as_not_right() -> None:
    def run(outcomes: dict[str, list[str]], run_id: str) -> RunResult:
        records = [
            _record(item, trial, outcome)
            for item, trials in outcomes.items()
            for trial, outcome in enumerate(trials, start=1)
        ]
        return RunResult(
            run_id=run_id, records=records, systems=["ledgerline"], models=["m"], trials=3
        )

    before = run({"q1": ["correct"] * 3, "q2": ["wrong"] * 3}, "before")
    after = run({"q1": ["correct"], "q2": ["correct", "correct"]}, "after")
    [pair] = compare_runs(before, after)
    assert (pair["before_right"], pair["after_right"]) == (1, 1)
    assert (pair["only_after"], pair["only_before"]) == (1, 1)


def test_a_run_on_named_items_plans_every_trial_for_spider_too() -> None:
    result = RunResult(
        run_id="r",
        records=[_record("spider:1", 1, "correct", schema="spider_car_1")],
        systems=["ledgerline"],
        models=["m"],
        trials=3,
        planned_trials={"spider_car_1": 3},
    )
    [row] = build(result)["question_level"]
    assert (row["right"]["n"], row["right"]["of"]) == (0, 1)


def _planned_run(outcomes: dict[str, list[str]], run_id: str = "r") -> RunResult:
    records = [
        _record(item, trial, outcome)
        for item, trials in outcomes.items()
        for trial, outcome in enumerate(trials, start=1)
    ]
    return RunResult(
        run_id=run_id,
        records=records,
        systems=["ledgerline"],
        models=["m"],
        trials=3,
        planned_items={"fieldservice": ["q1", "q2"]},
    )


def test_a_question_with_no_finished_trial_still_counts() -> None:
    # q2's three trials were all deferred, so it has no record at all.
    [row] = build(_planned_run({"q1": ["correct"] * 3}))["question_level"]
    assert (row["right"]["n"], row["right"]["of"]) == (1, 2)


def test_compare_runs_keeps_a_question_with_no_finished_trial() -> None:
    before = _planned_run({"q1": ["correct"] * 3, "q2": ["correct"] * 3}, "before")
    after = _planned_run({"q1": ["correct"] * 3}, "after")
    [pair] = compare_runs(before, after)
    assert pair["questions"] == 2
    assert (pair["before_right"], pair["after_right"]) == (2, 1)
    assert (pair["only_after"], pair["only_before"], pair["both"]) == (0, 1, 1)
