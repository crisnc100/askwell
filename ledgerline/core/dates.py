"""Relative-date resolution. Code does this, never the model.

Every period is half-open [start, end) in naive UTC. "this_*" periods and `ytd` end at
the reference time, since nothing after it exists.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

N_TOKENS: frozenset[str] = frozenset({"last_n_days", "last_n_weeks", "last_n_months"})


def naive_utc(moment: datetime) -> datetime:
    if moment.tzinfo is None:
        return moment
    return moment.astimezone(UTC).replace(tzinfo=None)


def _midnight(day: date) -> datetime:
    return datetime(day.year, day.month, day.day)


def add_months(moment: datetime, months: int) -> datetime:
    """Shift by whole months, clamping the day to the target month's length."""
    index = moment.year * 12 + (moment.month - 1) + months
    year, month = divmod(index, 12)
    month += 1
    next_month = date(year + (month == 12), month % 12 + 1, 1)
    last_day = (next_month - timedelta(days=1)).day
    return moment.replace(year=year, month=month, day=min(moment.day, last_day))


def _quarter_start(day: date) -> datetime:
    return datetime(day.year, 3 * ((day.month - 1) // 3) + 1, 1)


def resolve_relative(period: str, n: int | None, now: datetime) -> tuple[datetime, datetime]:
    """Resolve a relative period token to [start, end). Raises ValueError on bad input."""
    now = naive_utc(now)
    today = _midnight(now.date())
    if period in N_TOKENS:
        if n is None or n < 1:
            raise ValueError(f"{period} needs n >= 1")
        if period == "last_n_days":
            return now - timedelta(days=n), now
        if period == "last_n_weeks":
            return now - timedelta(weeks=n), now
        return add_months(now, -n), now
    if n is not None:
        raise ValueError(f"{period} takes no n")
    week_start = today - timedelta(days=today.weekday())
    month_start = today.replace(day=1)
    quarter_start = _quarter_start(today.date())
    year_start = today.replace(month=1, day=1)
    periods: dict[str, tuple[datetime, datetime]] = {
        "today": (today, today + timedelta(days=1)),
        "yesterday": (today - timedelta(days=1), today),
        "this_week": (week_start, now),
        "last_week": (week_start - timedelta(weeks=1), week_start),
        "this_month": (month_start, now),
        "last_month": (add_months(month_start, -1), month_start),
        "this_quarter": (quarter_start, now),
        "last_quarter": (add_months(quarter_start, -3), quarter_start),
        "this_year": (year_start, now),
        "ytd": (year_start, now),
        "last_year": (year_start.replace(year=year_start.year - 1), year_start),
    }
    if period not in periods:
        raise ValueError(f"unknown relative token {period!r}")
    return periods[period]
