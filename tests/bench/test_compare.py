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


def test_numbers_match_within_the_1e6_tolerance_on_both_sides_of_a_rounding_edge() -> None:
    # 1.00000051 and 1.00000049 differ by 2e-8 but round to different 6-decimal values.
    assert results_match([(1.00000051,)], [(Decimal("1.00000049"),)], ordered=False)
    assert results_match([(1.00000049,)], [(Decimal("1.00000051"),)], ordered=True)
    assert results_match([(2.0000005,)], [(2.0000014,)], ordered=False)  # 9e-7 apart
    assert not results_match([(2.0,)], [(2.0000021,)], ordered=False)  # 2.1e-6 apart
    # Large sums: float error stays within tolerance.
    assert results_match([(1369087.86,)], [(Decimal("1369087.8600000001"),)], ordered=False)
    # Multisets still pair rows correctly when values are within tolerance.
    got = [("a", 1.00000051), ("b", 5.0)]
    gold = [("b", Decimal("5.0000004")), ("a", Decimal("1.00000049"))]
    assert results_match(got, gold, ordered=False)
    assert not results_match([("a", 1.0), ("b", 5.0)], [("a", 5.0), ("b", 1.0)], ordered=False)


def test_tolerance_is_absolute_1e6_only() -> None:
    # A 0.0005 gap on a large number is far outside plan.md's 1e-6.
    assert not results_match([(1000000.0005,)], [(Decimal("1000000"),)], ordered=True)
    assert not results_match([(1000000.0005,)], [(Decimal("1000000"),)], ordered=False)
    assert results_match([(1000000.0000005,)], [(Decimal("1000000"),)], ordered=True)


def test_multiset_pairs_rows_whose_numbers_sort_differently() -> None:
    # Sorting both sides by their numbers pairs (4e-7, 10) with (4e-7, 20): wrong. The
    # right pairing treats 4e-7 and 0.0 as equal (within 1e-6) and matches on the 10/20.
    got = [(0.0000004, 10), (0.0, 20)]
    gold = [(0.0, 10), (0.0000004, 20)]
    assert results_match(got, gold, ordered=False)
    assert not results_match([(0.0000004, 10), (0.0, 30)], gold, ordered=False)
    many_got = [(i * 1e-7, i % 3) for i in range(9)]
    many_gold = [((8 - i) * 1e-7, (8 - i) % 3) for i in range(9)]
    assert results_match(many_got, many_gold, ordered=False)


def _brute_force(got: list[tuple[float, int]], gold: list[tuple[float, int]]) -> bool:
    from itertools import permutations as perms

    if len(got) != len(gold):
        return False
    return any(
        all(abs(a[0] - b[0]) <= 1e-6 and a[1] == b[1] for a, b in zip(got, order, strict=True))
        for order in perms(gold)
    )


def test_multiset_matching_agrees_with_brute_force() -> None:
    import random

    rng = random.Random(7)  # noqa: S311 - seeded test data, not security
    for _ in range(400):
        n = rng.randint(1, 6)
        got = [(rng.randint(0, 5) * 4e-7, rng.randint(0, 1)) for _ in range(n)]
        gold = [(rng.randint(0, 5) * 4e-7, rng.randint(0, 1)) for _ in range(n)]
        assert results_match(got, gold, ordered=False) == _brute_force(got, gold), (got, gold)
