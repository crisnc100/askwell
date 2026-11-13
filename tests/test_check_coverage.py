from __future__ import annotations

from typing import Any

from scripts.check_coverage import FLOORS, branch_percent, check


def _report(**pct: tuple[int, int]) -> dict[str, Any]:
    return {
        "files": {
            module: {
                "summary": {
                    "num_branches": total,
                    "covered_branches": covered,
                    "percent_covered": 100.0,
                }
            }
            for module, (covered, total) in pct.items()
        }
    }


def test_all_floors_met() -> None:
    report = _report(**dict.fromkeys(FLOORS, (100, 100)))
    assert check(report) == []


def test_a_module_below_its_floor_fails() -> None:
    report = _report(**dict.fromkeys(FLOORS, (100, 100)))
    report["files"]["askwell/core/validate.py"]["summary"]["covered_branches"] = 94
    assert check(report) == ["askwell/core/validate.py: branch coverage 94.0% < 95%"]


def test_a_missing_module_fails() -> None:
    assert len(check({"files": {}})) == len(FLOORS)


def test_no_branches_counts_as_full() -> None:
    assert branch_percent({"num_branches": 0}) == 100.0
