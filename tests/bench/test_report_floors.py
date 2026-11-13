"""The report's floor check: computed from the numbers, verdict text from evals/floors.yaml."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from askwell.bench.report import floor_checks


def _row(acc: tuple[int, int], wrong: tuple[int, int]) -> dict[str, object]:
    def rate(n: int, of: int) -> dict[str, object]:
        return {"n": n, "of": of, "rate": n / of, "ci95": [0.0, 1.0]}

    return {
        "schema": "fieldservice",
        "system": "ledgerline",
        "execution_accuracy": rate(*acc),
        "wrong_answer_rate_given_answered": rate(*wrong),
    }


FLOORS = """\
fieldservice:
  floors:
    execution_accuracy: {min: 0.80}
    wrong_answer_rate_given_answered: {max: 0.05}
  status_note: not met in v0.1 (simulated)
  cause: proxy answers
  next: refusal-first prompt
"""


def test_floors_met_and_not_met(tmp_path: Path) -> None:
    path = tmp_path / "floors.yaml"
    path.write_text(FLOORS)
    failing = floor_checks([_row((33, 43), (5, 38))], path)[0]
    assert not failing["met"]
    assert [c["met"] for c in failing["checks"]] == [False, False]
    assert failing["cause"] == "proxy answers"
    passing = floor_checks([_row((40, 43), (1, 40))], path)[0]
    assert passing["met"]
    assert [c["rule"] for c in passing["checks"]] == [">= 80%", "<= 5%"]


def test_no_floors_file_or_no_askwell_row(tmp_path: Path) -> None:
    assert floor_checks([_row((1, 1), (0, 1))], tmp_path / "missing.yaml") == []
    path = tmp_path / "floors.yaml"
    path.write_text(FLOORS)
    assert floor_checks([{"schema": "other", "system": "ledgerline"}], path) == []


def test_floor_heading_is_plain_words_in_code_and_in_every_committed_report() -> None:
    from askwell.bench import report as report_module

    data: dict[str, Any] = {
        "simulation": None,
        "run_id": "t",
        "notes": [],
        "status": "complete",
        "spent_usd": 0.0,
        "table": [],
        "floors": [
            {
                "schema": "fieldservice",
                "model": "m",
                "met": False,
                "checks": [],
                "status_note": None,
                "cause": None,
                "next": None,
            }
        ],
        "misses": [],
        "baseline_wins": [],
        "registry_hashes": {},
    }
    text = report_module.render_markdown(data)
    assert "## Floor check: fieldservice, m (v0.1 acceptance floor)" in text
    committed = [*report_module.REPORTS_DIR.glob("*.md"), report_module.FLOORS_FILE]
    assert len(committed) >= 3
    for path in committed:
        assert "plan.md" not in path.read_text(), path.name


HELD_OUT = (
    FLOORS
    + """\
fieldservice-held-out:
  schema: fieldservice
  gold: holdout-v02.jsonl
  floors:
    execution_accuracy: {min: 0.80}
  status_note: on held-out questions
"""
)


def _gold_row(gold: str | None, acc: tuple[int, int]) -> dict[str, object]:
    row = _row(acc, (0, 1))
    row["gold"] = gold
    return row


def test_an_entry_with_a_gold_file_checks_only_that_gold_file(tmp_path: Path) -> None:
    path = tmp_path / "floors.yaml"
    path.write_text(HELD_OUT)
    [held_out] = floor_checks([_gold_row("holdout-v02.jsonl", (10, 84))], path)
    assert held_out["gold"] == "holdout-v02.jsonl"
    assert held_out["status_note"] == "on held-out questions"
    assert [c["metric"] for c in held_out["checks"]] == ["execution_accuracy"]
    assert not held_out["met"]


def test_an_entry_with_no_gold_file_checks_only_the_default_gold(tmp_path: Path) -> None:
    path = tmp_path / "floors.yaml"
    path.write_text(HELD_OUT)
    for gold in (None, "fieldservice.jsonl"):
        [seen] = floor_checks([_gold_row(gold, (40, 43))], path)
        assert seen["gold"] is None
        assert seen["status_note"] == "not met in v0.1 (simulated)"
        assert len(seen["checks"]) == 2
    assert floor_checks([_gold_row("other.jsonl", (40, 43))], path) == []


def test_a_held_out_floor_names_its_gold_file_in_the_heading(tmp_path: Path) -> None:
    from askwell.bench import report as report_module

    path = tmp_path / "floors.yaml"
    path.write_text(HELD_OUT)
    floors = floor_checks([_gold_row("holdout-v02.jsonl", (10, 84))], path)
    data: dict[str, Any] = {
        "simulation": None,
        "run_id": "t",
        "notes": [],
        "status": "complete",
        "spent_usd": 0.0,
        "table": [],
        "floors": [{**floors[0], "model": "m"}],
        "misses": [],
        "baseline_wins": [],
        "registry_hashes": {},
    }
    text = report_module.render_markdown(data)
    assert "## Floor check: fieldservice, holdout-v02.jsonl, m (v0.1 acceptance floor)" in text
