"""Does a system's result match the gold result? (plan.md, Definitions, result comparison)

- Compare only as many columns as the gold has. A result with extra columns still
  matches if some of its columns, in any order, hold exactly the gold columns' values.
- Rows compare as a multiset, or as a sequence when the gold query has ORDER BY.
- Numbers compare as floats rounded to 6 decimal places. NULL never equals 0.
- Dates and datetimes compare as ISO text, so SQLite's date strings match Postgres dates.
- The gold is cut to the same row cap as the system's answer.
"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Sequence
from datetime import date, datetime
from decimal import Decimal
from itertools import permutations
from typing import Any

DECIMALS = 6
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
        return ("num", round(number, DECIMALS) + 0.0)  # + 0.0 turns -0.0 into 0.0
    if isinstance(value, datetime):
        return ("text", value.isoformat(sep=" "))
    if isinstance(value, date):
        return ("text", value.isoformat())
    text = str(value)
    if len(text) >= 11 and text[4] == "-" and text[7] == "-" and text[10] == "T":
        # ISO datetime text may use 'T' or a space between date and time.
        return ("text", text[:10] + " " + text[11:])
    return ("text", text)


def _rows(rows: Sequence[Sequence[Any]], columns: Sequence[int]) -> list[tuple[Cell, ...]]:
    return [tuple(_cell(row[i]) for i in columns) for row in rows]


def _same(a: list[tuple[Cell, ...]], b: list[tuple[Cell, ...]], ordered: bool) -> bool:
    if len(a) != len(b):
        return False
    if ordered:
        return a == b
    return Counter(a) == Counter(b)


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
