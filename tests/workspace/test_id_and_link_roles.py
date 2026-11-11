"""Which columns are IDs and which are links, and how each is typed.

- An ID column is checked for damaged values when the rest of it is numbers, like any
  other column; a column of labels such as '$5' is text.
- A link takes the type of the ID it points to before its values are judged.
- A column named after its own table (customer_id in customers.csv) is one of that
  table's ID names, never a link to itself.
- When some file cannot be read, the others are typed the same way.
"""

from __future__ import annotations

from pathlib import Path

from ledgerline.workspace.check import CheckResult, UploadedFile
from tests.workspace.conftest import check, csv_file

MAIN_TS = Path(__file__).resolve().parents[2] / "web" / "src" / "main.ts"


def problems(result: CheckResult, file: str) -> list[tuple[str, int | None, str | None]]:
    report = next(f for f in result.files if f.name == file)
    return [(p.code, p.row, p.column) for p in report.problems]


def test_a_shortened_number_in_a_numeric_id_column_is_reported() -> None:
    result = check(csv_file("accounts.csv", "id,label\n1,a\n2,b\n1.23457E+11,c\n"))
    assert problems(result, "accounts.csv") == [("bad_value", 4, "id")]
    fix = result.files[0].problems[0].fix
    assert fix.startswith("a spreadsheet shortened this number")
    assert not result.ok


def test_a_thousands_separator_in_a_numeric_id_column_is_reported() -> None:
    result = check(csv_file("accounts.csv", 'id,label\n1,a\n"1,234",b\n'))
    assert problems(result, "accounts.csv") == [("bad_value", 3, "id")]
    assert result.files[0].problems[0].fix == "remove the thousands separators: use 1234"


def test_ids_that_are_all_labels_stay_text() -> None:
    result = check(csv_file("codes.csv", "id,label\n$5,a\n45%,b\n"))
    assert result.ok
    assert result.tables[0].columns[0].type == "text"


def test_a_business_key_named_after_its_own_table_is_not_a_link() -> None:
    result = check(csv_file("customers.csv", "id,customer_id,name\n1,C-001,a\n2,C-002,b\n"))
    assert result.ok, problems(result, "customers.csv")
    plan = result.tables[0]
    assert plan.id_column == "id"
    assert plan.links == []
    assert plan.columns[1].type == "text"


def test_the_singular_and_table_names_on_their_own_table_are_never_links() -> None:
    for header in ("node_id", "nodes_id"):
        result = check(csv_file("nodes.csv", f"id,{header}\n1,x9\n2,x1\n"))
        assert result.ok, (header, problems(result, "nodes.csv"))
        assert result.tables[0].links == []


def test_the_prepare_page_states_the_rule() -> None:
    text = MAIN_TS.read_text(encoding="utf-8")
    assert "named after its own table" in text


def test_an_unreadable_file_does_not_change_how_the_others_are_typed() -> None:
    result = check(
        csv_file("parents.csv", "id,label\n$5,a\n$6,b\n"),
        csv_file("children.csv", "id,parent_id\n1,$5\n2,$6\n"),
        UploadedFile("broken.csv", b""),
    )
    assert problems(result, "children.csv") == []
    assert problems(result, "parents.csv") == []
    assert [p.code for p in next(f for f in result.files if f.name == "broken.csv").problems] == [
        "empty_file"
    ]


def test_an_unreadable_file_still_leaves_damaged_values_reported() -> None:
    result = check(
        csv_file("orders.csv", "id,total\n1,12\n2,$5\n"),
        UploadedFile("broken.csv", b""),
    )
    assert problems(result, "orders.csv") == [("bad_value", 3, "total")]
