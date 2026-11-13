"""Reading a cell takes time in proportion to its length. Every pattern that classifies
cells runs on 10,000-character adversarial cells (long runs of digits, commas and
symbols ending in a character that does not match) well inside 0.1 s, and a cell over
the length limit is reported without being classified at all."""

from __future__ import annotations

import re
import time

import pytest

from askwell.workspace import check as check_module
from askwell.workspace import rules
from askwell.workspace.limits import Limits
from tests.workspace.conftest import check, csv_file

N = 10_000
ADVERSARIAL = [
    "9" * (N - 1) + "x",
    "1," * (N // 2 - 1) + "x",
    "$" + "9" * (N - 2) + "x",
    "$" + "1," * (N // 2 - 1) + "x",
    "9" * (N - 2) + "%x",
    "1," * (N // 2 - 2) + "1%x",
    "9" * (N // 2) + "." + "9" * (N // 2 - 2) + "x",
    "1" * (N - 3) + "E+x",
    "1/" * (N // 2 - 1) + "x",
    "2025-01-01 " + "9" * (N - 12) + "x",
    "-" * (N - 1) + "x",
    "+" * (N - 1) + "9",
    "0" * (N - 1) + "x",
]
PATTERNS = sorted(
    (name, value) for name, value in vars(rules).items() if isinstance(value, re.Pattern)
)


@pytest.mark.parametrize(("name", "pattern"), PATTERNS, ids=[n for n, _ in PATTERNS])
def test_every_pattern_is_linear_on_adversarial_cells(name: str, pattern: re.Pattern[str]) -> None:
    for cell in ADVERSARIAL:
        start = time.perf_counter()
        pattern.fullmatch(cell)
        pattern.match(cell)
        elapsed = time.perf_counter() - start
        assert elapsed < 0.1, (name, cell[:20], elapsed)


def test_kind_and_fixes_are_fast_on_adversarial_cells() -> None:
    for cell in ADVERSARIAL:
        start = time.perf_counter()
        rules.kind(cell)
        rules.number_fix(cell)
        rules.is_null(cell)
        assert time.perf_counter() - start < 0.1, cell[:20]


def test_a_cell_over_the_limit_is_never_classified(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[int] = []
    real = check_module.kind

    def spy(cell: str) -> str:
        seen.append(len(cell))
        return real(cell)

    monkeypatch.setattr(check_module, "kind", spy)
    result = check(
        csv_file("items.csv", f"id,note\n1,{'9' * 50}x\n"), limits=Limits(max_cell_chars=10)
    )
    assert [p.code for f in result.files for p in f.problems] == ["cell_too_long"]
    assert seen
    assert max(seen) <= 10
