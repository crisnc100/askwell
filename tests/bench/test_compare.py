"""Result comparison rules (plan.md, Definitions)."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from ledgerline.bench.compare import results_match


def test_multiset_vs_sequence() -> None:
    gold = [(1, "a"), (2, "b")]
    assert results_match([(2, "b"), (1, "a")], gold, ordered=False)
    assert not results_match([(2, "b"), (1, "a")], gold, ordered=True)
    assert not results_match([(1, "a"), (1, "a"), (2, "b")], gold, ordered=False)


def test_numbers_decimal_float_and_null() -> None:
    assert results_match([(1.0000001,)], [(Decimal("1.0000001"),)], ordered=False)
    assert results_match([(2,)], [(2.0,)], ordered=False)
    assert not results_match([(1.01,)], [(1.0,)], ordered=False)
    assert not results_match([(0,)], [(None,)], ordered=False)
    assert results_match([(None,)], [(None,)], ordered=False)


def test_dates_compare_as_iso_text() -> None:
    assert results_match([("2026-01-05",)], [(date(2026, 1, 5),)], ordered=False)
    assert results_match([("2026-01-05T10:00:00",)], [(datetime(2026, 1, 5, 10),)], ordered=False)


def test_extra_columns_match_only_when_gold_columns_are_inside() -> None:
    gold = [("north", 3), ("south", 5)]
    assert results_match([(3, "north", 9), (5, "south", 9)], gold, ordered=False)
    assert not results_match([(3, "north"), (6, "south")], gold, ordered=False)
    assert not results_match([("north",), ("south",)], gold, ordered=False)


def test_row_cap_applies_to_gold_too() -> None:
    gold = [(i,) for i in range(10)]
    assert results_match([(i,) for i in range(3)], gold, ordered=True, row_cap=3)


def test_empty_results() -> None:
    assert results_match([], [], ordered=False)
    assert not results_match([(1,)], [], ordered=False)
    assert not results_match([], [(1,)], ordered=False)


def test_a_midnight_datetime_equals_the_same_date() -> None:
    """Postgres date_trunc on a DATE returns a midnight timestamp (with time zone); a
    builder that casts to DATE returns the date. Same value, different representation."""
    from datetime import UTC

    month = date(2025, 1, 1)
    assert results_match([(month, 1)], [(datetime(2025, 1, 1, tzinfo=UTC), 1)], ordered=True)
    assert results_match([(month,)], [(datetime(2025, 1, 1),)], ordered=True)
    assert results_match([("2025-01-01 00:00:00",)], [(month,)], ordered=True)
    assert not results_match([(month,)], [(datetime(2025, 1, 1, 0, 0, 1),)], ordered=True)
