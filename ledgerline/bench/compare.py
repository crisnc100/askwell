"""Does a system's result match the gold result? (plan.md, Definitions, result comparison)

- Compare only as many columns as the gold has. A result with extra columns still
  matches if some of its columns, in any order, hold exactly the gold columns' values.
- Rows compare as a multiset, or as a sequence when the gold query has ORDER BY.
- Numbers compare as floats and match within 1e-6 (absolute; 1e-9 relative for very
  large sums). NULL never equals 0.
- Dates and datetimes compare as ISO text, so SQLite's date strings match Postgres dates,
  and a datetime at exactly midnight UTC matches the same date.
- The gold is cut to the same row cap as the system's answer.
"""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from collections.abc import Sequence
from datetime import UTC, date, datetime
from decimal import Decimal
from itertools import permutations
from typing import Any

ABS_TOLERANCE = 1e-6
REL_TOLERANCE = 1e-9
MAX_COLUMN_ORDERS = 5000

Cell = tuple[str, Any]


def _cell(value: Any) -> Cell:
    if value is None:
        return ("null", None)
    if isinstance(value, bool):
        return ("num", float(value))
    if isinstance(value, int | float | Decimal):
        number = float(value)
        if math.isnan(number):
            return ("nan", None)
        return ("num", number + 0.0)  # + 0.0 turns -0.0 into 0.0
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            value = value.astimezone(UTC).replace(tzinfo=None)
        return ("text", _midnight_as_date(value.isoformat(sep=" ")))
    if isinstance(value, date):
        return ("text", value.isoformat())
    text = str(value)
    if len(text) >= 11 and text[4] == "-" and text[7] == "-" and text[10] == "T":
        # ISO datetime text may use 'T' or a space between date and time.
        text = text[:10] + " " + text[11:]
    return ("text", _midnight_as_date(text))


def _midnight_as_date(text: str) -> str:
    """'2025-01-01 00:00:00' (any zero fraction) reads as '2025-01-01': a date and its
    midnight are the same value in different clothes (Postgres date_trunc returns the
    timestamp, a DATE cast returns the date)."""
    if len(text) >= 19 and text[4] == "-" and text[10] == " " and text[11:19] == "00:00:00":
        rest = text[19:]
        if rest.strip(".0") == "":
            return text[:10]
    return text


def _rows(rows: Sequence[Sequence[Any]], columns: Sequence[int]) -> list[tuple[Cell, ...]]:
    return [tuple(_cell(row[i]) for i in columns) for row in rows]


Row = tuple[Cell, ...]


def _close(a: Row, b: Row) -> bool:
    for (kind_a, x), (kind_b, y) in zip(a, b, strict=True):
        if kind_a != kind_b:
            return False
        if kind_a == "num":
            if not math.isclose(x, y, rel_tol=REL_TOLERANCE, abs_tol=ABS_TOLERANCE):
                return False
        elif x != y:
            return False
    return True


def _signature(row: Row) -> tuple[Any, ...]:
    """Everything but the numbers: rows can only match within the same signature."""
    return tuple((kind, None if kind == "num" else value) for kind, value in row)


def _numbers(row: Row) -> tuple[float, ...]:
    return tuple(value for kind, value in row if kind == "num")


def _same(a: list[Row], b: list[Row], ordered: bool) -> bool:
    if len(a) != len(b):
        return False
    if ordered:
        return all(_close(x, y) for x, y in zip(a, b, strict=True))
    groups_a: dict[tuple[Any, ...], list[Row]] = defaultdict(list)
    groups_b: dict[tuple[Any, ...], list[Row]] = defaultdict(list)
    for row in a:
        groups_a[_signature(row)].append(row)
    for row in b:
        groups_b[_signature(row)].append(row)
    if Counter({k: len(v) for k, v in groups_a.items()}) != Counter(
        {k: len(v) for k, v in groups_b.items()}
    ):
        return False
    # Within a signature, pair rows in numeric order; within-tolerance values sort alike.
    for key, rows_a in groups_a.items():
        left = sorted(rows_a, key=_numbers)
        right = sorted(groups_b[key], key=_numbers)
        if not all(_close(x, y) for x, y in zip(left, right, strict=True)):
            return False
    return True


def results_match(
    got: Sequence[Sequence[Any]],
    gold: Sequence[Sequence[Any]],
    *,
    ordered: bool,
    row_cap: int | None = None,
) -> bool:
    if row_cap is not None:
        gold = gold[:row_cap]
        got = got[:row_cap]
    gold_width = len(gold[0]) if gold else 0
    got_width = len(got[0]) if got else 0
    if not gold:
        return not got
    if got_width < gold_width:
        return False
    target = _rows(gold, range(gold_width))
    for count, order in enumerate(permutations(range(got_width), gold_width)):
        if count >= MAX_COLUMN_ORDERS:
            break
        if _same(_rows(got, order), target, ordered):
            return True
    return False
