"""The report's floor check: computed from the numbers, verdict text from evals/floors.yaml."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ledgerline.bench.report import floor_checks


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


def test_no_floors_file_or_no_ledgerline_row(tmp_path: Path) -> None:
    assert floor_checks([_row((1, 1), (0, 1))], tmp_path / "missing.yaml") == []
    path = tmp_path / "floors.yaml"
    path.write_text(FLOORS)
    assert floor_checks([{"schema": "other", "system": "ledgerline"}], path) == []


def test_floor_heading_is_plain_words_in_code_and_in_every_committed_report() -> None:
    from ledgerline.bench import report as report_module

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
