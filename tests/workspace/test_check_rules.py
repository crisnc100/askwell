"""L16: one named test per Check rule, each with a minimal bad file. Every message names
the file, the row and column where there is one, what is wrong and the fix."""

from __future__ import annotations

from ledgerline.workspace.check import CheckResult, Problem, UploadedFile
from ledgerline.workspace.limits import Limits
from tests.workspace.conftest import check, csv_file


def only_problem(result: CheckResult, code: str) -> Problem:
    problems = [p for f in result.files for p in f.problems if p.code == code]
    assert len(problems) == 1, [p.text() for f in result.files for p in f.problems]
    return problems[0]


def assert_names(problem: Problem, file: str, row: int | None, column: str | None) -> None:
    assert (problem.file, problem.row, problem.column) == (file, row, column)
    assert problem.fix
    text = problem.text()
    assert file in text
    if row is not None:
        assert f"row {row}" in text
    if column is not None:
        assert f"column {column}" in text
    assert "Fix: " in text


def test_encoding_not_utf8() -> None:
    bad = UploadedFile("items.csv", "id,label\n1,ok\n2,caf\xe9\n".encode("latin-1"))
    result = check(bad)
    problem = only_problem(result, "not_utf8")
    assert_names(problem, "items.csv", 3, None)
    assert "UTF-8" in problem.fix
    assert not result.ok
    assert result.tables == []


def test_empty_file() -> None:
    assert_names(
        only_problem(check(csv_file("items.csv", "  \n")), "empty_file"), "items.csv", None, None
    )


def test_header_only_file_has_no_rows() -> None:
    problem = only_problem(check(csv_file("items.csv", "id,label\n")), "no_rows")
    assert_names(problem, "items.csv", None, None)


def test_header_missing() -> None:
    problem = only_problem(
        check(csv_file("items.csv", "1,2025-01-02\n2,2025-01-03\n")), "no_header"
    )
    assert_names(problem, "items.csv", 1, None)


def test_header_blank_column_name() -> None:
    problem = only_problem(check(csv_file("items.csv", "id,,label\n1,2,a\n")), "blank_header")
    assert_names(problem, "items.csv", 1, None)
    assert "column 2" in problem.message


def test_header_names_collide_after_slugging() -> None:
    result = check(csv_file("items.csv", "id,Order Date,order_date\n1,2025-01-01,2025-01-02\n"))
    problem = only_problem(result, "duplicate_header")
    assert_names(problem, "items.csv", 1, "order_date")
    assert "'Order Date'" in problem.message


def test_blank_header_does_not_hide_a_name_collision() -> None:
    result = check(csv_file("items.csv", "id,,Order Date,order_date\n1,2,2025-01-01,2025-01-02\n"))
    assert_names(only_problem(result, "blank_header"), "items.csv", 1, None)
    problem = only_problem(result, "duplicate_header")
    assert_names(problem, "items.csv", 1, "order_date")
    assert not result.ok


def test_semicolon_delimiter_is_named() -> None:
    problem = only_problem(check(csv_file("items.csv", "id;label\n1;a\n")), "wrong_delimiter")
    assert_names(problem, "items.csv", 1, None)
    assert "semicolons" in problem.message
    assert "commas" in problem.fix


def test_ragged_row() -> None:
    problem = only_problem(check(csv_file("items.csv", "id,label\n1,a\n2,b,c\n")), "ragged_row")
    assert_names(problem, "items.csv", 3, None)
    assert "3 values but there are 2 columns" in problem.message


def test_unclosed_quote() -> None:
    problem = only_problem(check(csv_file("items.csv", 'id,label\n1,"a"b\n')), "bad_quoting")
    assert_names(problem, "items.csv", 2, None)
    assert "quotes" in problem.fix


def test_number_with_thousands_separator() -> None:
    result = check(csv_file("items.csv", 'id,total\n1,12\n2,"1,234.50"\n'))
    problem = only_problem(result, "bad_value")
    assert_names(problem, "items.csv", 3, "total")
    assert problem.fix == "remove the thousands separators: use 1234.50"


def test_number_with_currency_symbol() -> None:
    problem = only_problem(check(csv_file("items.csv", "id,total\n1,12\n2,$5.25\n")), "bad_value")
    assert_names(problem, "items.csv", 3, "total")
    assert problem.fix == "remove the currency symbol: use 5.25"


def test_number_with_percent_sign() -> None:
    problem = only_problem(check(csv_file("items.csv", "id,rate\n1,0.5\n2,45%\n")), "bad_value")
    assert_names(problem, "items.csv", 3, "rate")
    assert problem.fix == "remove the % sign: use 45 (or the fraction, 0.45)"


def test_number_shortened_by_a_spreadsheet() -> None:
    result = check(csv_file("items.csv", "id,account\n1,12345678901\n2,1.2E+11\n"))
    problem = only_problem(result, "bad_value")
    assert_names(problem, "items.csv", 3, "account")
    assert "shortened" in problem.fix


def test_date_in_another_form() -> None:
    result = check(csv_file("invoices.csv", "id,invoice_date\n1,2025-03-01\n14,3/4/25\n"))
    problem = only_problem(result, "bad_value")
    assert_names(problem, "invoices.csv", 3, "invoice_date")
    assert problem.message == "'3/4/25' is not a date in the form YYYY-MM-DD"
    assert problem.fix == "use 2025-03-04 (if it means March 4, 2025)"


def test_date_that_does_not_exist() -> None:
    result = check(csv_file("invoices.csv", "id,invoice_date\n1,2025-03-01\n2,2025-02-30\n"))
    problem = only_problem(result, "bad_value")
    assert_names(problem, "invoices.csv", 3, "invoice_date")
    assert problem.message == "'2025-02-30' is not a real date"


def test_datetime_with_time_zone() -> None:
    text = "id,seen_at\n1,2025-03-01 10:00\n2,2025-03-02T09:30:00Z\n"
    problem = only_problem(check(csv_file("visits.csv", text)), "bad_value")
    assert_names(problem, "visits.csv", 3, "seen_at")
    assert problem.fix == "use a space between date and time and no time zone: 2025-03-02 09:30:00"


def test_mostly_dates_with_a_word() -> None:
    rows = "".join(f"{i},2025-01-{i:02d}\n" for i in range(1, 11)) + "11,soon\n"
    problem = only_problem(check(csv_file("tasks.csv", "id,due\n" + rows)), "bad_value")
    assert_names(problem, "tasks.csv", 12, "due")
    assert "rest of the column is dates" in problem.message


def test_table_without_id_column() -> None:
    problem = only_problem(check(csv_file("items.csv", "label,size\na,1\n")), "no_id_column")
    assert_names(problem, "items.csv", None, None)
    assert "id or items_id" in problem.fix


def test_blank_id() -> None:
    problem = only_problem(check(csv_file("items.csv", "id,label\n1,a\n,b\n")), "blank_id")
    assert_names(problem, "items.csv", 3, "id")


def test_duplicate_id() -> None:
    problem = only_problem(check(csv_file("items.csv", "id,label\n7,a\n7,b\n")), "duplicate_id")
    assert_names(problem, "items.csv", 3, "id")
    assert "also on row 2" in problem.message


def test_link_value_of_the_wrong_type() -> None:
    result = check(
        csv_file("customers.csv", "id,label\n1,a\n2,b\n"),
        csv_file("orders.csv", "id,customer_id\n10,1\n11,002\n"),
    )
    problem = only_problem(result, "link_type")
    assert_names(problem, "orders.csv", 3, "customer_id")
    assert problem.fix == "write it without leading zeros: 2"


def test_link_with_no_match_is_a_warning_and_still_loads() -> None:
    result = check(
        csv_file("customers.csv", "id,label\n1,a\n"),
        csv_file("orders.csv", "id,customer_id\n10,1\n11,9\n"),
    )
    problem = only_problem(result, "orphan_link")
    assert problem.level == "warning"
    assert_names(problem, "orders.csv", 3, "customer_id")
    assert result.ok
    assert len(result.tables) == 2


def test_two_files_become_the_same_table() -> None:
    result = check(csv_file("Orders.csv", "id\n1\n"), csv_file("orders.CSV", "id\n2\n"))
    for report in result.files:
        assert [p.code for p in report.problems] == ["duplicate_table"]
        assert "'orders'" in report.problems[0].message
    assert not result.ok


def test_reserved_table_name() -> None:
    problem = only_problem(check(csv_file("sqlite_stat.csv", "id\n1\n")), "reserved_name")
    assert_names(problem, "sqlite_stat.csv", None, None)


def test_file_too_large() -> None:
    limits = Limits(max_file_bytes=20)
    result = check(csv_file("items.csv", "id,label\n1,abcdefghijklmnop\n"), limits=limits)
    assert_names(only_problem(result, "file_too_large"), "items.csv", None, None)


def test_too_many_columns() -> None:
    header = ",".join(f"c{i}" for i in range(5))
    result = check(csv_file("items.csv", f"id,{header}\n"), limits=Limits(max_columns=5))
    assert_names(only_problem(result, "too_many_columns"), "items.csv", 1, None)


def test_too_many_rows() -> None:
    rows = "".join(f"{i}\n" for i in range(1, 6))
    result = check(csv_file("items.csv", "id\n" + rows), limits=Limits(max_rows=3))
    assert_names(only_problem(result, "too_many_rows"), "items.csv", 5, None)


def test_cell_too_long() -> None:
    result = check(
        csv_file("items.csv", f"id,note\n1,{'x' * 11}\n"), limits=Limits(max_cell_chars=10)
    )
    assert_names(only_problem(result, "cell_too_long"), "items.csv", 2, "note")


def test_cell_past_the_csv_reader_limit() -> None:
    result = check(csv_file("items.csv", f"id,note\n1,{'x' * 200_000}\n"))
    problem = only_problem(result, "cell_too_long")
    assert_names(problem, "items.csv", 2, None)


def test_messages_are_capped_per_file() -> None:
    rows = "".join(f"{i},$1\n" for i in range(1, 26))
    result = check(csv_file("items.csv", "id,total\n" + rows))
    report = result.files[0].to_dict()
    assert len(report["problems"]) == 20  # type: ignore[arg-type]
    assert report["more"] == 5
    assert report["more_text"] == "and 5 more like this"
    assert report["errors"] == 25


# Files that are messy but valid: each passes and gets the expected types.


def test_bom_crlf_quoted_newlines_and_trailing_commas_pass() -> None:
    text = '﻿id,note,amount,\r\n1,"a, b\r\nc",1.5,\r\n2,,-3,\r\n'
    result = check(csv_file("Items (final).CSV", text))
    assert result.ok
    plan = result.tables[0]
    assert plan.name == "items_final"
    assert [(c.name, c.type) for c in plan.columns] == [
        ("id", "integer"),
        ("note", "text"),
        ("amount", "number"),
    ]
    assert plan.rows == [["1", "a, b\r\nc", "1.5"], ["2", None, "-3"]]


def test_null_spellings() -> None:
    result = check(csv_file("items.csv", "id,qty\n1,NULL\n2,na\n3,N/A\n4,-\n5,\n6,  \n7,4\n"))
    assert result.ok
    assert [r[1] for r in result.tables[0].rows] == [None] * 6 + ["4"]
    assert result.tables[0].columns[1].type == "integer"


def test_leading_zeros_make_text_and_links_follow_the_id_type() -> None:
    result = check(
        csv_file("stores.csv", "store_id,zip\n001,02134\n002,10001\n"),
        csv_file("visits.csv", "id,store_id\n1,001\n2,2\n"),
    )
    assert result.ok
    stores, visits = result.tables
    assert stores.id_column == "store_id"
    assert stores.columns[1].type == "text"
    assert visits.columns[1].type == "text"
    assert [(p.code, p.row) for p in result.files[1].problems] == [("orphan_link", 3)]


def test_link_table_without_its_own_id() -> None:
    result = check(
        csv_file("orders.csv", "order_id,day\n1,2025-01-01\n"),
        csv_file("products.csv", "id,label\n5,x\n"),
        csv_file("order_lines.csv", "order_id,product_id,qty\n1,5,2\n"),
    )
    assert result.ok
    lines = next(t for t in result.tables if t.name == "order_lines")
    assert lines.id_column is None
    assert [(link.column, link.table) for link in lines.links] == [
        ("order_id", "orders"),
        ("product_id", "products"),
    ]


def test_datetime_column_may_mix_dates() -> None:
    result = check(csv_file("visits.csv", "id,seen_at\n1,2025-03-01\n2,2025-03-02 09:30\n"))
    assert result.ok
    assert result.tables[0].columns[1].type == "datetime"
