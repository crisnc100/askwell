"""ADR-004's selection rule: the gates, "clearly worse", the exhaustion case and the second
model, on synthetic eval records."""

from __future__ import annotations

from typing import Any

from scripts.select_model import Candidate, candidates, choose


def _cand(model: str, cost: float, correct: int, **kw: Any) -> Candidate:
    base: dict[str, Any] = {
        "questions": 67,
        "answerable": 43,
        "wrong": 2,
        "refusals_caught": 24,
        "refusal_items": 24,
        "calls": 100,
        "unreadable": 0,
        "p50_ms": 1000.0,
    }
    base.update(kw)
    return Candidate(model=model, cost_per_question=cost, correct=correct, **base)


def test_each_gate_rejects_on_its_own_threshold() -> None:
    assert _cand("a/x", 1, 30, unreadable=2).gate_failures() == []
    assert _cand("a/x", 1, 30, unreadable=3).gate_failures() == ["unreadable"]
    assert _cand("a/x", 1, 30, refusals_caught=23).gate_failures() == []
    assert _cand("a/x", 1, 30, refusals_caught=22).gate_failures() == ["refusal recall"]
    assert _cand("a/x", 1, 30, p50_ms=3000.0).gate_failures() == []
    assert _cand("a/x", 1, 30, p50_ms=3001.0).gate_failures() == ["latency"]


def test_the_cheapest_not_clearly_worse_wins() -> None:
    found = [
        _cand("a/cheap", 0.001, 27),  # 3 behind: not clearly worse
        _cand("b/mid", 0.002, 28),
        _cand("c/best", 0.01, 30),
    ]
    choice = choose(found)
    assert choice.best.model == "c/best"
    assert choice.default.model == "a/cheap"
    assert choice.second is not None
    assert choice.second.model == "c/best"


def test_four_behind_on_correct_or_wrong_is_clearly_worse() -> None:
    behind = choose([_cand("a/cheap", 0.001, 26), _cand("c/best", 0.01, 30)])
    assert behind.default.model == "c/best"
    more_wrong = choose([_cand("a/cheap", 0.001, 30, wrong=6), _cand("c/best", 0.01, 30)])
    assert more_wrong.default.model == "c/best"


def test_a_gated_out_model_is_never_picked_when_another_passes() -> None:
    choice = choose([_cand("a/cheap", 0.001, 30, p50_ms=5000.0), _cand("c/ok", 0.01, 25)])
    assert choice.default.model == "c/ok"
    assert [c.model for c in choice.eligible] == ["c/ok"]
    assert choice.note == ""


def test_if_nothing_passes_the_best_rung_ships_and_says_so() -> None:
    choice = choose(
        [_cand("a/x", 0.001, 20, p50_ms=5000.0), _cand("c/y", 0.01, 30, refusals_caught=10)]
    )
    assert choice.eligible == []
    assert choice.default.model == "c/y"
    assert "No candidate passed" in choice.note


def test_records_are_scored_from_the_ledgerline_system_only() -> None:
    def rec(system: str, category: str, outcome: str, parse_errors: int = 0) -> dict[str, Any]:
        return {
            "system": system,
            "model": "a/x",
            "category": category,
            "outcome": outcome,
            "cost_usd": 0.01,
            "latency_ms": 500.0,
            "detail": {"attempts": 1 + parse_errors, "parse_errors": parse_errors},
        }

    found = candidates(
        [
            rec("ledgerline", "in_schema", "correct"),
            rec("ledgerline", "in_schema", "refused", parse_errors=2),
            rec("ledgerline", "should_refuse", "refused"),
            rec("ledgerline", "out_of_schema", "wrong"),
            rec("oneshot", "in_schema", "correct"),
        ]
    )
    (only,) = found
    assert (only.correct, only.answerable, only.wrong) == (1, 2, 1)
    assert (only.refusals_caught, only.refusal_items) == (1, 2)
    assert (only.unreadable, only.calls) == (2, 6)
