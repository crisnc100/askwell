"""How single cells are read: kinds, column types, conversion and the spelled-out fixes."""

from __future__ import annotations

import pytest

from askwell.workspace.rules import (
    column_type,
    convert,
    date_fix,
    intended_type,
    kind,
    number_fix,
)


@pytest.mark.parametrize(
    ("cell", "expected"),
    [
        ("42", "int"),
        ("-0", "int"),
        ("+7", "int"),
        ("00123", "zero_int"),
        ("007.5", "zero_int"),
        (str(2**63), "big_int"),
        ("1.50", "num"),
        (".5", "num"),
        ("0.12345678901234567890", "long_num"),
        ("2025-03-04", "date"),
        ("2025-03-04 10:30", "datetime"),
        ("2025-03-04 10:30:15", "datetime"),
        ("2025-13-01", "bad_date"),
        ("2025-03-04 25:00", "bad_date"),
        ("1,234", "bad_number"),
        ("€5", "bad_number"),
        ("5 €", "bad_number"),
        ("12.5%", "bad_number"),
        ("1.2E+11", "bad_number"),
        ("3/4/25", "bad_date"),
        ("2025/3/4", "bad_date"),
        ("2025-03-04T10:30:00+02:00", "bad_date"),
        ("hello", "text"),
    ],
)
def test_kind(cell: str, expected: str) -> None:
    assert kind(cell) == expected


def test_column_types() -> None:
    assert column_type(set()) == "text"
    assert column_type({"int"}) == "integer"
    assert column_type({"int", "num"}) == "number"
    assert column_type({"date"}) == "date"
    assert column_type({"date", "datetime"}) == "datetime"
    assert column_type({"int", "zero_int"}) == "text"
    assert column_type({"num", "long_num"}) == "text"
    assert intended_type({"int", "zero_int", "bad_number"}) is None
    assert intended_type({"int", "bad_number"}) == "number"
    assert intended_type({"date", "bad_date"}) == "date"
    assert intended_type({"text", "bad_date"}) is None


def test_convert() -> None:
    assert convert("+7", "integer") == 7
    assert convert("1.50", "number") == 1.5
    assert convert("2025-03-04", "date") == "2025-03-04"
    assert convert("2025-03-04", "datetime") == "2025-03-04 00:00:00"
    assert convert("2025-03-04 10:30", "datetime") == "2025-03-04 10:30:00"
    assert convert(" anything ", "text") == " anything "
    for cell, ctype in (
        ("1.5", "integer"),
        ("x", "number"),
        ("2025-03-04 10:00", "date"),
        ("soon", "datetime"),
    ):
        with pytest.raises(ValueError, match="is not"):
            convert(cell, ctype)  # type: ignore[arg-type]


def test_number_fixes() -> None:
    assert number_fix("1,234") == "remove the thousands separators: use 1234"
    assert number_fix("$1,234.50") == "remove the currency symbol: use 1234.50"
    assert number_fix("5%") == "remove the % sign: use 5 (or the fraction, 0.05)"
    assert number_fix("1,2,3%") == "remove the % sign: use 123 (or the fraction, 1.23)"
    assert "shortened" in number_fix("4.5e10")


def test_date_fixes() -> None:
    assert date_fix("3/4/25") == "use 2025-03-04 (if it means March 4, 2025)"
    assert date_fix("25/12/2024") == "use 2024-12-25 (if it means December 25, 2024)"
    assert date_fix("31/31/2024") == "use the form YYYY-MM-DD"
    assert date_fix("2025/3/4") == "use dashes: 2025-03-04"
    assert date_fix("2025/2/30") == "use dashes: YYYY-MM-DD"
    assert date_fix("2025-02-30") == "this date does not exist; check the day and the month"
    assert date_fix("2025-03-04T10:30Z") == (
        "use a space between date and time and no time zone: 2025-03-04 10:30"
    )


@pytest.mark.parametrize(
    "cell",
    [
        "1.5" + "0" * 40,
        "0." + "0" * 40 + "25",
        "-1234567890123456.5" + "0" * 30,
    ],
)
def test_a_long_decimal_a_float_stores_exactly_is_a_number(cell: str) -> None:
    assert len(cell) > 40
    assert kind(cell) == "num"
    assert convert(cell, "number") == float(cell)


def test_a_decimal_with_more_than_17_significant_digits_is_never_a_number() -> None:
    assert kind("0.12345678901234567") == "long_num"
    assert kind("1" + "0" * 30 + ".5") == "long_num"


@pytest.mark.parametrize("space", ["\u00a0", "\u202f"])
def test_no_break_spaces_in_money_and_percent_are_damaged_numbers(space: str) -> None:
    for cell, fix in (
        (f"12.5{space}%", "remove the % sign: use 12.5 (or the fraction, 0.125)"),
        (f"5{space}€", "remove the currency symbol: use 5"),
        (f"${space}1,234.50", "remove the currency symbol: use 1234.50"),
    ):
        assert kind(cell) == "bad_number", cell
        assert number_fix(cell) == fix
    assert intended_type({"num", kind(f"5{space}€")}) == "number"
