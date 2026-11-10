"""Row comparison for tests: Decimal/float within tolerance, dates as ISO, NULL is NULL."""

from __future__ import annotations

import math
from collections.abc import Sequence
from datetime import date, datetime
from decimal import Decimal
from typing import Any

Cell = float | str | bool | int | None


def _cell(value: Any) -> Cell:
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, Decimal | float | int):
        return float(value)
    if isinstance(value, datetime):
        return value.isoformat(sep=" ")
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def normalise(rows: Sequence[Sequence[Any]], ordered: bool) -> list[tuple[Cell, ...]]:
    out = [tuple(_cell(v) for v in row) for row in rows]
    if ordered:
        return out

    def key(row: tuple[Cell, ...]) -> tuple[str, ...]:
        return tuple(f"{v:.6f}" if isinstance(v, float) else repr(v) for v in row)

    return sorted(out, key=key)


def same_rows(a: Sequence[Sequence[Any]], b: Sequence[Sequence[Any]], ordered: bool) -> bool:
    left, right = normalise(a, ordered), normalise(b, ordered)
    if len(left) != len(right):
        return False
    for row_a, row_b in zip(left, right, strict=True):
        if len(row_a) != len(row_b):
            return False
        for x, y in zip(row_a, row_b, strict=True):
            if isinstance(x, float) and isinstance(y, float):
                if not math.isclose(x, y, rel_tol=1e-9, abs_tol=1e-6):
                    return False
            elif x != y:
                return False
    return True
