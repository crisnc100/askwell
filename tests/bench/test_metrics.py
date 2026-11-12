"""Metric definitions and Wilson intervals."""

from __future__ import annotations

import pytest

from askwell.bench.metrics import ItemOutcome, summarise, wilson


def test_wilson_known_values() -> None:
    low, high = wilson(8, 10)  # type: ignore[misc]
    assert low == pytest.approx(0.4902, abs=1e-4)
    assert high == pytest.approx(0.9433, abs=1e-4)
    assert wilson(0, 0) is None
    zero = wilson(0, 20)
    assert zero is not None
    assert zero[0] == 0.0


def _o(category: str, outcome: str) -> ItemOutcome:
    return ItemOutcome("x", category, outcome, 0.01, 100.0)  # type: ignore[arg-type]


def test_summary_rates() -> None:
    outcomes = [
        _o("in_schema", "correct"),
        _o("in_schema", "correct"),
        _o("in_schema", "wrong"),
        _o("in_schema", "refused"),
        _o("in_schema", "error"),
        _o("should_refuse", "refused"),
        _o("out_of_schema", "wrong"),
        _o("in_schema", "pending"),
    ]
    s = summarise(outcomes)
    assert s["items"] == 7
    assert s["pending"] == 1
    assert (s["coverage"]["n"], s["coverage"]["of"]) == (4, 5)
    assert (s["execution_accuracy"]["n"], s["execution_accuracy"]["of"]) == (2, 5)
    assert (s["accuracy_given_attempted"]["n"], s["accuracy_given_attempted"]["of"]) == (2, 4)
    assert (s["false_refusal_rate"]["n"], s["false_refusal_rate"]["of"]) == (1, 5)
    # Answered = returned rows: 2 correct, 1 wrong in_schema, 1 wrong refusal item.
    assert (
        s["wrong_answer_rate_given_answered"]["n"],
        s["wrong_answer_rate_given_answered"]["of"],
    ) == (2, 4)
    assert (s["refusal_recall"]["n"], s["refusal_recall"]["of"]) == (1, 2)
    assert (s["execution_error_rate"]["n"], s["execution_error_rate"]["of"]) == (1, 7)
    assert s["mean_cost_usd"] == pytest.approx(0.01)
    assert s["p50_latency_ms"] == 100.0
