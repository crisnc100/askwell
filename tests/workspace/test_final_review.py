"""The last review round: non-ASCII digits, the fix for a slash timestamp, and two
files that become the same table."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from ledgerline.workspace import rules
from ledgerline.workspace.check import UploadedFile
from ledgerline.workspace.rules import date_fix, kind
from tests.workspace.conftest import check, csv_file
from tests.workspace.test_roundtrip import assert_round_trip


@pytest.mark.parametrize(
    "cell",
    [
        "\uff10\uff10\uff11\uff12\uff13",  # full-width 00123
        "\u0661\u0662\u0663",  # Arabic-Indic 123
        "\uff11.\uff15",
        "\uff12\uff10\uff12\uff15-\uff10\uff13-\uff10\uff14",
    ],
)
def test_digits_outside_ascii_are_text(cell: str) -> None:
    assert kind(cell) == "text"


def test_full_width_digits_keep_their_exact_text(tmp_path: Path) -> None:
    files = [
        UploadedFile(
            "items.csv",
            "id,code\n1,\uff10\uff10\uff11\uff12\uff13\n2,\uff11\uff12\uff13\n".encode(),
        )
    ]
    result = check(*files)
    assert result.ok
    assert result.tables[0].columns[1].type == "text"
    assert_round_trip(files, tmp_path / "data.sqlite")


def test_every_rules_pattern_reads_ascii_digits_only() -> None:
    for name, value in vars(rules).items():
        if isinstance(value, re.Pattern):
            assert value.flags & re.ASCII, name


def test_a_slash_timestamp_fix_keeps_the_time() -> None:
    assert date_fix("3/4/25 14:30") == "use 2025-03-04 14:30 (if it means March 4, 2025)"
    assert date_fix("3/4/2025 9:05:07") == "use 2025-03-04 09:05:07 (if it means March 4, 2025)"
    assert date_fix("3/4/25 2pm") == "use 2025-03-04 HH:MM (if it means March 4, 2025)"


def test_two_files_with_different_columns_that_become_one_table_are_reported() -> None:
    result = check(
        csv_file("Orders.csv", "id\n1\n"),
        csv_file("orders.csv", "label,day,id\n1,2025-01-01,7\n"),
    )
    assert not result.ok
    for report in result.files:
        assert [p.code for p in report.problems] == ["duplicate_table"]


def test_duplicate_tables_do_not_stop_the_other_files_being_checked() -> None:
    result = check(
        csv_file("Orders.csv", "id,total\n1,5\n"),
        csv_file("orders.csv", "id,customer_id\n1,2\n"),
        csv_file("visits.csv", "id,day\n1,3/4/25\n"),
    )
    visits = next(f for f in result.files if f.name == "visits.csv")
    assert [(p.code, p.row) for p in visits.problems] == [("bad_value", 2)]
