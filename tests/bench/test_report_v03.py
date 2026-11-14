"""How v0.3 results are reported (builds/v03/plan.md, "How results are reported"):
question-level accuracy (right in a majority of trials) with an interval on distinct
questions, and a paired McNemar test between two runs on the same questions."""

from __future__ import annotations

from typing import Any

import pytest

from askwell.bench.metrics import mcnemar_exact, question_level
from askwell.bench.report import build, compare_runs, render_markdown
from askwell.bench.report_schema import Report
from askwell.bench.run import RunResult


def _record(item: str, trial: int, outcome: str, system: str = "ledgerline") -> dict[str, Any]:
    return {
        "key": f"{system}|{item}|{trial}",
        "schema_id": "fieldservice",
        "model": "m",
        "trial": trial,
        "system": system,
        "item_id": item,
        "gold": "holdout-v03.jsonl",
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


def _run(outcomes: dict[str, list[str]], run_id: str = "r") -> RunResult:
    records = [
        _record(item, trial, outcome)
        for item, trials in outcomes.items()
        for trial, outcome in enumerate(trials, start=1)
    ]
    return RunResult(run_id=run_id, records=records, systems=["ledgerline"], models=["m"], trials=3)


def test_a_question_is_right_when_right_in_most_of_its_trials() -> None:
    outcomes = {
        "q1": ["correct", "correct", "wrong"],
        "q2": ["correct", "refused", "wrong"],
        "q3": ["correct", "correct", "correct"],
    }
    assert question_level(_run(outcomes).records) == (2, 3)


def test_mcnemar_exact_is_the_two_sided_binomial() -> None:
    assert mcnemar_exact(0, 0) == 1.0
    assert mcnemar_exact(10, 0) == pytest.approx(2 / 2**10)
    assert mcnemar_exact(3, 5) == pytest.approx(min(1.0, 2 * (1 + 8 + 28 + 56) / 2**8))
    assert mcnemar_exact(5, 3) == mcnemar_exact(3, 5)


def test_the_report_carries_question_level_accuracy() -> None:
    result = _run({"q1": ["correct"] * 3, "q2": ["wrong", "correct", "wrong"]})
    report = build(result)
    Report.model_validate(report)
    [row] = report["question_level"]
    assert (row["right"]["n"], row["right"]["of"]) == (1, 2)
    assert "Question-level accuracy" in render_markdown(report)


def test_a_one_trial_report_keeps_its_old_shape() -> None:
    result = _run({"q1": ["correct"]})
    result.trials = 1
    report = build(result)
    assert "question_level" not in report
    assert "Question-level accuracy" not in render_markdown(report)


def test_compare_runs_pairs_questions() -> None:
    before = _run({"q1": ["wrong"] * 3, "q2": ["wrong"] * 3, "q3": ["correct"] * 3}, "before")
    after = _run({"q1": ["correct"] * 3, "q2": ["correct"] * 3, "q3": ["correct"] * 3}, "after")
    [pair] = compare_runs(before, after)
    assert (pair["only_after"], pair["only_before"], pair["both"], pair["neither"]) == (2, 0, 1, 0)
    assert pair["p_value"] == pytest.approx(mcnemar_exact(2, 0))
    assert (pair["before_right"], pair["after_right"], pair["questions"]) == (1, 3, 3)
