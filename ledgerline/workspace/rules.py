"""How one CSV cell is read: null spellings, value kinds, column types and conversion.

Check and the loader both use this module, so a value Check accepts is always a value
the loader can store. A column's type comes from all its non-null values:

- integer: every value is a whole number with no leading zero that fits in 64 bits.
- number: every value is a whole or decimal number that a float stores exactly. A
  whole number past 2^53 does not fit a float exactly, so mixed with decimals it makes
  the column text instead.
- date: every value is `YYYY-MM-DD`.
- datetime: every value is `YYYY-MM-DD HH:MM[:SS]` or a date (a date is its midnight).
- text: anything else. One leading zero (like `00123`) makes the column text, so IDs
  and zip codes keep their zeros.

Values that look like a damaged number or date (`1,234`, `$5`, `45%`, `1.2E+11`,
`3/4/25`) are not silently read as text when the rest of the column is numbers or
dates: Check reports each one with its fix.

Every pattern reads ASCII digits only (re.ASCII), so digits from other scripts, such as
full-width digits, make a column text and keep their exact text.

Every pattern here runs in time proportional to the cell's length: no two quantifiers
can match the same characters, so a long cell that almost matches cannot make the
matcher try exponentially many ways. Digit strings longer than any 64-bit number are
classified by length before Python parses them.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Literal

ColumnType = Literal["integer", "number", "date", "datetime", "text"]
Kind = Literal[
    "int",  # a plain whole number a float stores exactly (at most 2^53 either way)
    "wide_int",  # a whole number past 2^53 that still fits in 64 bits
    "zero_int",  # a whole or decimal number with a leading zero, like 00123
    "big_int",  # a whole number past 64 bits
    "num",  # a plain decimal number a float stores exactly
    "long_num",  # a decimal number a float would round
    "date",
    "datetime",
    "bad_number",  # a number with a separator, currency, % or an exponent
    "bad_date",  # a date in another form, or a date that does not exist
    "text",
]

NULL_SPELLINGS: frozenset[str] = frozenset({"", "null", "na", "n/a", "-"})
INT64_MIN, INT64_MAX = -(2**63), 2**63 - 1
FLOAT_EXACT = 2**53
# More digits than any 64-bit number has; longer digit strings are never parsed.
_MAX_INT_DIGITS = 19
# A decimal longer than this cannot be stored exactly in a float anyway.
_MAX_NUM_CHARS = 40

_INT = re.compile(r"[-+]?\d+", re.ASCII)
_NUM = re.compile(r"[-+]?(?:\d+\.\d*|\.\d+)", re.ASCII)
_LEADING_ZERO = re.compile(r"[-+]?0\d", re.ASCII)
_DATE = re.compile(r"\d{4}-\d{2}-\d{2}", re.ASCII)
_DATETIME = re.compile(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}(?::\d{2})?", re.ASCII)

_THOUSANDS = re.compile(r"[-+]?\d{1,3}(?:,\d{3})+(?:\.\d+)?", re.ASCII)
# A number written loosely: digits and commas, then an optional fraction (or only a
# fraction). The comma run and the fraction cannot overlap, so matching is linear.
_LOOSE = r"(?:\d[\d,]*(?:\.\d+)?|\.\d+)"
_CURRENCY = re.compile(rf"[-+]?[$€£¥]\s?{_LOOSE}|[-+]?{_LOOSE}\s?[$€£¥]", re.ASCII)
_PERCENT = re.compile(rf"[-+]?{_LOOSE}\s?%", re.ASCII)
_EXPONENT = re.compile(r"[-+]?\d+(?:\.\d+)?[eE][-+]?\d+", re.ASCII)
_SLASH_DATE = re.compile(r"(\d{1,2})[/.-](\d{1,2})[/.-](\d{2}|\d{4})(?:[ T](.*))?", re.ASCII)
_CLOCK = re.compile(r"(\d{1,2}):(\d{2})(?::(\d{2}))?", re.ASCII)
_YMD_SLASH = re.compile(r"(\d{4})/(\d{1,2})/(\d{1,2})", re.ASCII)
_ISO_ZONED = re.compile(
    r"(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2}(?::\d{2})?)(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?",
    re.ASCII,
)

NUMBER_KINDS: frozenset[str] = frozenset({"int", "num"})
INTEGER_KINDS: frozenset[str] = frozenset({"int", "wide_int"})
DATE_KINDS: frozenset[str] = frozenset({"date", "datetime"})
# Values that read cleanly as a number or a date.
CLEAN_KINDS: frozenset[str] = NUMBER_KINDS | INTEGER_KINDS | DATE_KINDS


def is_null(cell: str) -> bool:
    """Blank (or only spaces), NULL, NA, N/A and -, in any case."""
    return cell.strip().lower() in NULL_SPELLINGS


def kind(cell: str) -> Kind:
    """What one non-null cell looks like."""
    if _INT.fullmatch(cell):
        if _LEADING_ZERO.match(cell):
            return "zero_int"
        if len(cell.lstrip("+-")) > _MAX_INT_DIGITS:
            return "big_int"
        value = int(cell)
        if not INT64_MIN <= value <= INT64_MAX:
            return "big_int"
        return "int" if abs(value) <= FLOAT_EXACT else "wide_int"
    if _NUM.fullmatch(cell):
        if _LEADING_ZERO.match(cell):
            return "zero_int"
        if len(cell) > _MAX_NUM_CHARS:
            return "long_num"
        return "num" if _float_is_exact(cell) else "long_num"
    if _DATE.fullmatch(cell):
        return "date" if _valid_date(cell) else "bad_date"
    if _DATETIME.fullmatch(cell):
        return "datetime" if _valid_datetime(cell) else "bad_date"
    if (
        _THOUSANDS.fullmatch(cell)
        or _CURRENCY.fullmatch(cell)
        or _PERCENT.fullmatch(cell)
        or _EXPONENT.fullmatch(cell)
    ):
        return "bad_number"
    if _SLASH_DATE.fullmatch(cell) or _YMD_SLASH.fullmatch(cell) or _ISO_ZONED.fullmatch(cell):
        return "bad_date"
    return "text"


def _float_is_exact(cell: str) -> bool:
    try:
        return Decimal(repr(float(cell))) == Decimal(cell)
    except (InvalidOperation, ValueError):
        return False


def _valid_date(cell: str) -> bool:
    try:
        date.fromisoformat(cell)
    except ValueError:
        return False
    return True


def _valid_datetime(cell: str) -> bool:
    try:
        datetime.fromisoformat(cell)
    except ValueError:
        return False
    return True


def column_type(kinds: set[str]) -> ColumnType:
    """The type of a column whose non-null values have these kinds."""
    if not kinds:
        return "text"
    if kinds <= INTEGER_KINDS:
        return "integer"
    if kinds <= NUMBER_KINDS:
        return "number"
    if kinds == {"date"}:
        return "date"
    if kinds <= DATE_KINDS:
        return "datetime"
    return "text"


def intended_type(kinds: set[str]) -> ColumnType | None:
    """The type a column was meant to have when some of its values are damaged numbers
    or dates and every other value is a clean one; None when nothing is damaged."""
    if "zero_int" in kinds:
        return None
    if "bad_number" in kinds and kinds <= NUMBER_KINDS | INTEGER_KINDS | {"bad_number"}:
        return "number"
    if "bad_date" in kinds and kinds <= DATE_KINDS | {"bad_date"}:
        return "date"
    return None


Stored = int | float | str


def convert(cell: str, ctype: ColumnType) -> Stored:
    """The stored value of a non-null cell in a column of `ctype`. Raises ValueError if
    the cell is not a value of that type; Check runs this on every cell first."""
    if ctype == "text":
        return cell
    found = kind(cell)
    if ctype == "integer":
        if found not in INTEGER_KINDS:
            raise ValueError(f"{cell!r} is not a whole number")
        return int(cell)
    if ctype == "number":
        if found not in NUMBER_KINDS:
            raise ValueError(f"{cell!r} is not a number")
        return float(cell)
    if ctype == "date":
        if found != "date":
            raise ValueError(f"{cell!r} is not a YYYY-MM-DD date")
        return cell
    if found not in DATE_KINDS:
        raise ValueError(f"{cell!r} is not a date or date and time")
    # One stored form, so equal moments are equal text in SQLite.
    return datetime.fromisoformat(cell).strftime("%Y-%m-%d %H:%M:%S")


def number_fix(cell: str) -> str:
    """The fix for a damaged number, spelled out for this value."""
    if _EXPONENT.fullmatch(cell):
        return (
            "a spreadsheet shortened this number; format the column as a whole number "
            "(or as text) and export again"
        )
    plain = re.sub(r"[\s,$€£¥%]", "", cell, flags=re.ASCII)
    if _PERCENT.fullmatch(cell):
        try:
            fraction = format(Decimal(plain) / 100, "f")
        except InvalidOperation:
            return f"remove the % sign: use {plain}"
        return f"remove the % sign: use {plain} (or the fraction, {fraction})"
    if _CURRENCY.fullmatch(cell):
        return f"remove the currency symbol: use {plain}"
    return f"remove the thousands separators: use {plain}"


def is_iso_shaped(cell: str) -> bool:
    """True for `YYYY-MM-DD` or `YYYY-MM-DD HH:MM[:SS]`, whether or not the date exists."""
    return bool(_DATE.fullmatch(cell) or _DATETIME.fullmatch(cell))


def date_fix(cell: str) -> str:
    """The fix for a damaged or impossible date, spelled out for this value."""
    if is_iso_shaped(cell):
        return "this date does not exist; check the day and the month"
    zoned = _ISO_ZONED.fullmatch(cell)
    if zoned:
        day, clock = zoned.group(1), zoned.group(2)
        return f"use a space between date and time and no time zone: {day} {clock}"
    ymd = _YMD_SLASH.fullmatch(cell)
    if ymd:
        year, month, day = (int(g) for g in ymd.groups())
        return f"use dashes: {_iso(year, month, day) or 'YYYY-MM-DD'}"
    slash = _SLASH_DATE.fullmatch(cell)
    assert slash is not None
    first, second, year_text, time_text = slash.groups()
    year = int(year_text) + (2000 if len(year_text) == 2 else 0)
    a, b = int(first), int(second)
    # Month first unless the first number cannot be a month.
    month, day = (a, b) if a <= 12 else (b, a)
    suggestion = _iso(year, month, day)
    if suggestion is None:
        return "use the form YYYY-MM-DD"
    if time_text is not None:
        suggestion = f"{suggestion} {_clock(time_text)}"
    spoken = f"{date(year, month, day):%B} {day}, {year}"
    return f"use {suggestion} (if it means {spoken})"


def _clock(text: str) -> str:
    """A time of day in the accepted HH:MM[:SS] form, or a placeholder if it is not
    one (like 2pm)."""
    found = _CLOCK.fullmatch(text.strip())
    if found is None:
        return "HH:MM"
    hour, minute, second = found.groups()
    out = f"{int(hour):02d}:{minute}"
    return out + (f":{second}" if second else "")


def _iso(year: int, month: int, day: int) -> str | None:
    try:
        return date(year, month, day).isoformat()
    except ValueError:
        return None
