"""Relative-date resolution against the reference time (2026-06-30T00:00Z, a Tuesday)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from askwell.core.dates import add_months, naive_utc, resolve_relative

NOW = datetime(2026, 6, 30, tzinfo=UTC)
D = datetime


@pytest.mark.parametrize(
    ("token", "n", "start", "end"),
    [
        ("today", None, D(2026, 6, 30), D(2026, 7, 1)),
        ("yesterday", None, D(2026, 6, 29), D(2026, 6, 30)),
        ("last_n_days", 90, D(2026, 4, 1), D(2026, 6, 30)),
        ("last_n_weeks", 2, D(2026, 6, 16), D(2026, 6, 30)),
        ("last_n_months", 12, D(2025, 6, 30), D(2026, 6, 30)),
        ("last_n_months", 6, D(2025, 12, 30), D(2026, 6, 30)),
        ("this_week", None, D(2026, 6, 29), D(2026, 6, 30)),
        ("last_week", None, D(2026, 6, 22), D(2026, 6, 29)),
        ("this_month", None, D(2026, 6, 1), D(2026, 6, 30)),
        ("last_month", None, D(2026, 5, 1), D(2026, 6, 1)),
        ("this_quarter", None, D(2026, 4, 1), D(2026, 6, 30)),
        ("last_quarter", None, D(2026, 1, 1), D(2026, 4, 1)),
        ("this_year", None, D(2026, 1, 1), D(2026, 6, 30)),
        ("ytd", None, D(2026, 1, 1), D(2026, 6, 30)),
        ("last_year", None, D(2025, 1, 1), D(2026, 1, 1)),
    ],
)
def test_tokens_match_the_gold_conventions(
    token: str, n: int | None, start: datetime, end: datetime
) -> None:
    assert resolve_relative(token, n, NOW) == (start, end)


def test_last_quarter_from_the_first_quarter_crosses_the_year() -> None:
    assert resolve_relative("last_quarter", None, D(2026, 2, 10)) == (D(2025, 10, 1), D(2026, 1, 1))


def test_add_months_clamps_the_day() -> None:
    assert add_months(D(2026, 3, 31), -1) == D(2026, 2, 28)
    assert add_months(D(2024, 3, 31), -1) == D(2024, 2, 29)
    assert add_months(D(2025, 12, 15), 1) == D(2026, 1, 15)
    assert add_months(D(2026, 1, 31), -2) == D(2025, 11, 30)


@pytest.mark.parametrize(
    ("token", "n"),
    [("last_n_days", None), ("last_n_months", 0), ("last_month", 1), ("next_month", None)],
)
def test_bad_tokens_raise(token: str, n: int | None) -> None:
    with pytest.raises(ValueError, match=token):
        resolve_relative(token, n, NOW)


def test_naive_utc_converts_offsets() -> None:
    assert naive_utc(datetime.fromisoformat("2026-01-01T02:00:00+02:00")) == D(2026, 1, 1)
    assert naive_utc(D(2026, 1, 1, 5)) == D(2026, 1, 1, 5)
