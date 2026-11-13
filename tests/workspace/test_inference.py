"""Column types and links on the edge cases: integers too big for a float, links to IDs
that look like damaged numbers, very long headers and digit strings, and negative IDs
with leading zeros. A second round-trip property mixes all of them into generated
files."""

from __future__ import annotations

import csv
import io
import sqlite3
from pathlib import Path
from typing import Any

from hypothesis import given, settings
from hypothesis import strategies as st

from askwell.workspace.check import UploadedFile
from askwell.workspace.limits import Limits
from askwell.workspace.load import load_tables
from tests.workspace.conftest import check, csv_file
from tests.workspace.test_roundtrip import assert_round_trip


def codes(result: Any) -> list[str]:
    return [p.code for f in result.files for p in f.problems]


def stored(tmp_path: Path, result: Any, table: str, column: str) -> list[Any]:
    db = tmp_path / "data.sqlite"
    load_tables(result.tables, db)
    with sqlite3.connect(db) as conn:
        return [r[0] for r in conn.execute(f'SELECT "{column}" FROM "{table}" ORDER BY rowid')]


def test_an_integer_past_two_to_the_53_with_a_decimal_makes_text(tmp_path: Path) -> None:
    result = check(csv_file("items.csv", "id,amount\n1,9007199254740993\n2,1.5\n"))
    assert result.ok
    assert result.tables[0].columns[1].type == "text"
    assert stored(tmp_path, result, "items", "amount") == ["9007199254740993", "1.5"]


def test_big_integers_alone_stay_whole_numbers(tmp_path: Path) -> None:
    result = check(csv_file("items.csv", "id,amount\n1,9007199254740993\n2,-5\n"))
    assert result.tables[0].columns[1].type == "integer"
    assert stored(tmp_path, result, "items", "amount") == [9007199254740993, -5]


def test_a_link_to_ids_that_look_like_damaged_numbers_passes() -> None:
    result = check(
        csv_file("parents.csv", "id,label\n$5,a\n$6,b\n"),
        csv_file("children.csv", "id,parent_id\n1,$5\n2,$6\n"),
    )
    assert codes(result) == []
    assert result.ok
    assert result.tables[0].columns[0].type == "text"
    assert result.tables[1].columns[1].type == "text"


def test_a_header_over_the_cell_limit_is_refused() -> None:
    result = check(csv_file("items.csv", f"id,{'h' * 11}\n1,2\n"), limits=Limits(max_cell_chars=10))
    problems = [p for f in result.files for p in f.problems]
    assert [(p.code, p.row) for p in problems] == [("header_too_long", 1)]
    assert problems[0].fix


def test_a_column_name_over_128_characters_is_refused() -> None:
    result = check(csv_file("items.csv", f"id,{'Long name ' * 14}\n1,2\n"))
    problems = [p for f in result.files for p in f.problems]
    assert [(p.code, p.row) for p in problems] == [("column_name_too_long", 1)]
    assert "128" in problems[0].fix


def test_a_5000_digit_value_does_not_crash(tmp_path: Path) -> None:
    digits = "1" * 5000
    result = check(csv_file("items.csv", f"id,code\n1,{digits}\n2,{digits}.5\n"))
    assert result.ok
    assert result.tables[0].columns[1].type == "text"
    assert stored(tmp_path, result, "items", "code") == [digits, f"{digits}.5"]


def test_the_leading_zero_fix_keeps_the_minus_sign() -> None:
    result = check(
        csv_file("accounts.csv", "id,label\n-7,a\n"),
        csv_file("moves.csv", "id,account_id\n1,-007\n"),
    )
    [problem] = [p for f in result.files for p in f.problems]
    assert problem.code == "link_type"
    assert problem.fix == "write it without leading zeros: -7"


# The edge cases above, mixed into generated files.

BIG = st.integers(2**53 + 1, 2**63 - 1).map(str)
DECIMAL = st.decimals(min_value=-1000, max_value=1000, places=2, allow_nan=False).map(str)
LONG_DIGITS = st.integers(4400, 5000).map(lambda n: "9" * n)
DAMAGED_LOOKING = st.sampled_from(["$5", "1,234", "45%", "1.2E+11", "3/4/25"])
NEGATIVE_PADDED = st.integers(1, 99).map(lambda n: f"-0{n}")
MIXED = st.one_of(BIG, DECIMAL, LONG_DIGITS, NEGATIVE_PADDED, st.sampled_from(["", "NA"]))


@st.composite
def edge_files(draw: st.DrawFn) -> list[UploadedFile]:
    n = draw(st.integers(2, 6))
    ids = draw(
        st.lists(
            DAMAGED_LOOKING | st.integers(1, 10**6).map(str), min_size=n, max_size=n, unique=True
        )
    )
    if any(not i.isdigit() for i in ids):
        ids[0] = "x" + ids[0]  # keeps a mixed column text, so every ID is a label
    mixed = draw(st.lists(MIXED, min_size=n, max_size=n))
    links = draw(st.lists(st.sampled_from(ids) | st.just(""), min_size=n, max_size=n))
    parents = io.StringIO()
    writer = csv.writer(parents, lineterminator="\n")
    writer.writerow(["id", "mixed"])
    writer.writerows(zip(ids, mixed, strict=True))
    children = io.StringIO()
    writer = csv.writer(children, lineterminator="\n")
    writer.writerow(["id", "parent_id"])
    writer.writerows(zip(range(1, n + 1), links, strict=True))
    return [
        UploadedFile("parents.csv", parents.getvalue().encode()),
        UploadedFile("children.csv", children.getvalue().encode()),
    ]


@settings(max_examples=100, deadline=None)
@given(edge_files())
def test_edge_cases_that_pass_check_load_and_round_trip(
    tmp_path_factory: Any, files: list[UploadedFile]
) -> None:
    assert_round_trip(files, tmp_path_factory.mktemp("edges") / "data.sqlite")
