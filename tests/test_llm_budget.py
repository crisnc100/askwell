"""Budget guard over a run: abort at the hard stop, partial results, resume from checkpoint."""

from __future__ import annotations

from pathlib import Path

import pytest

from ledgerline.llm.budget import BudgetGuard, Checkpoint, ItemResult, run_checkpointed
from ledgerline.llm.errors import BudgetExceededError

ITEMS = [f"q{i}" for i in range(10)]


def make_work(cost_per_item: float, calls: list[str]):
    def work(item: str, guard: BudgetGuard) -> ItemResult:
        guard.precheck(cost_per_item)
        calls.append(item)
        guard.charge(cost_per_item)
        return ItemResult(record={"id": item, "answer": item.upper()}, cost_usd=cost_per_item)

    return work


def test_guard_precheck_and_charge() -> None:
    guard = BudgetGuard(1.0)
    guard.precheck(1.0)  # exactly at the limit is allowed
    guard.charge(0.6)
    assert guard.remaining_usd == pytest.approx(0.4)
    with pytest.raises(BudgetExceededError):
        guard.precheck(0.5)


def test_negative_budget_is_rejected() -> None:
    with pytest.raises(ValueError, match="budget"):
        BudgetGuard(-1)


def test_run_aborts_at_budget_with_partial_results(tmp_path: Path) -> None:
    calls: list[str] = []
    outcome = run_checkpointed(
        ITEMS, str, make_work(0.1, calls), Checkpoint(tmp_path / "run.jsonl"), budget_usd=0.35
    )
    assert outcome.aborted
    assert outcome.is_partial
    assert "budget stop" in (outcome.abort_reason or "")
    assert calls == ["q0", "q1", "q2"]
    assert [r["id"] for r in outcome.records] == ["q0", "q1", "q2"]
    assert outcome.spent_usd == pytest.approx(0.3)
    assert outcome.spent_usd <= 0.35


def test_resume_skips_finished_items_and_keeps_total_budget(tmp_path: Path) -> None:
    checkpoint = Checkpoint(tmp_path / "run.jsonl")
    first_calls: list[str] = []
    first = run_checkpointed(ITEMS, str, make_work(0.1, first_calls), checkpoint, budget_usd=0.35)
    assert first.aborted

    # Same budget: spend already in the checkpoint counts, so nothing more runs.
    stuck_calls: list[str] = []
    stuck = run_checkpointed(ITEMS, str, make_work(0.1, stuck_calls), checkpoint, budget_usd=0.35)
    assert stuck_calls == []
    assert stuck.aborted
    assert stuck.resumed == 3

    # Raised budget: resumes after q2 and finishes.
    more_calls: list[str] = []
    done = run_checkpointed(ITEMS, str, make_work(0.1, more_calls), checkpoint, budget_usd=1.05)
    assert more_calls == ITEMS[3:]
    assert not done.aborted
    assert not done.is_partial
    assert done.resumed == 3
    assert done.newly_completed == 7
    assert [r["id"] for r in done.records] == ITEMS
    assert done.spent_usd == pytest.approx(1.0)


def test_spend_from_an_item_stopped_midway_still_counts(tmp_path: Path) -> None:
    """An item that made one paid call, then hit the stop on its second, is not lost."""
    checkpoint = Checkpoint(tmp_path / "run.jsonl")

    def two_calls(item: str, guard: BudgetGuard) -> ItemResult:
        for _ in range(2):
            guard.precheck(0.1)
            guard.charge(0.1)
        return ItemResult(record={"id": item}, cost_usd=0.2)

    outcome = run_checkpointed(ITEMS, str, two_calls, checkpoint, budget_usd=0.35)
    assert outcome.aborted
    assert [r["id"] for r in outcome.records] == ["q0"]
    done, spent = checkpoint.load()
    assert list(done) == ["q0"]
    assert spent == pytest.approx(0.3)


def test_spend_from_a_crashed_item_counts_and_the_error_propagates(tmp_path: Path) -> None:
    checkpoint = Checkpoint(tmp_path / "run.jsonl")

    def crash(item: str, guard: BudgetGuard) -> ItemResult:
        guard.charge(0.05)
        raise RuntimeError("provider exploded")

    with pytest.raises(RuntimeError, match="exploded"):
        run_checkpointed(ITEMS, str, crash, checkpoint, budget_usd=1.0)
    done, spent = checkpoint.load()
    assert done == {}
    assert spent == pytest.approx(0.05)


def test_unreported_spend_is_charged(tmp_path: Path) -> None:
    def sneaky(item: str, guard: BudgetGuard) -> ItemResult:
        return ItemResult(record={"id": item}, cost_usd=0.2)

    outcome = run_checkpointed(
        ITEMS[:3], str, sneaky, Checkpoint(tmp_path / "r.jsonl"), budget_usd=10
    )
    assert outcome.spent_usd == pytest.approx(0.6)


def test_torn_last_line_is_ignored_on_resume(tmp_path: Path) -> None:
    path = tmp_path / "run.jsonl"
    checkpoint = Checkpoint(path)
    calls: list[str] = []
    run_checkpointed(ITEMS[:2], str, make_work(0.1, calls), checkpoint, budget_usd=1)
    with path.open("a") as fh:
        fh.write('{"key": "q2", "cost_')  # killed mid-write
    resumed_calls: list[str] = []
    outcome = run_checkpointed(ITEMS[:3], str, make_work(0.1, resumed_calls), checkpoint, 1)
    assert resumed_calls == ["q2"]
    assert outcome.resumed == 2


def test_two_resumes_after_a_torn_line_keep_progress_and_spend(tmp_path: Path) -> None:
    """A torn tail is repaired on load, so appends after it stay readable on later resumes."""
    path = tmp_path / "run.jsonl"
    checkpoint = Checkpoint(path)
    calls: list[str] = []
    run_checkpointed(ITEMS[:2], str, make_work(0.1, calls), checkpoint, budget_usd=10)
    with path.open("a") as fh:
        fh.write('{"key": "q2", "cost_usd": 0.1, "rec')  # killed mid-write

    first_resume: list[str] = []
    one = run_checkpointed(ITEMS[:4], str, make_work(0.1, first_resume), checkpoint, 10)
    assert first_resume == ["q2", "q3"]
    assert one.spent_usd == pytest.approx(0.4)

    second_resume: list[str] = []
    two = run_checkpointed(ITEMS[:6], str, make_work(0.1, second_resume), checkpoint, 10)
    assert second_resume == ["q4", "q5"]
    assert two.resumed == 4
    assert [r["id"] for r in two.records] == ITEMS[:6]
    assert two.spent_usd == pytest.approx(0.6)
    done, spent = Checkpoint(path).load()
    assert sorted(done) == ITEMS[:6]
    assert spent == pytest.approx(0.6)


def test_append_after_a_torn_line_without_load_is_still_readable(tmp_path: Path) -> None:
    path = tmp_path / "run.jsonl"
    checkpoint = Checkpoint(path)
    checkpoint.append("q0", 0.1, {"id": "q0"})
    with path.open("a") as fh:
        fh.write('{"key": "q1", "co')
    checkpoint.append("q1", 0.2, {"id": "q1"})
    checkpoint.append("q2", 0.3, {"id": "q2"})
    done, spent = checkpoint.load()
    assert sorted(done) == ["q0", "q1", "q2"]
    assert spent == pytest.approx(0.6)
