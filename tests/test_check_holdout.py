"""The held-out check, on synthetic items over a small SQLite file: never on a real
held-out set, which only the orchestrator runs it on."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

import pytest

from askwell.gold import GoldItem
from scripts.check_holdout import (
    check_items,
    database_runner,
    key_columns,
    order_items,
    outer_limit,
    with_limit,
    word_runs,
)

SEEN = ["How many invoices are still unpaid at the end of this month?"]


@pytest.fixture
def runner(tmp_path: Path) -> Any:
    path = tmp_path / "shop.sqlite"
    con = sqlite3.connect(path)
    con.executescript(
        """
        CREATE TABLE cities (id INTEGER PRIMARY KEY, name TEXT, jobs INTEGER, revenue REAL);
        INSERT INTO cities VALUES
          (1, 'Akron', 50, 10.5), (2, 'Boise', 40, 20.25), (3, 'Cary', 40, 30.0),
          (4, 'Dover', 30, 40.0), (5, 'Erie', 20, 40.0000000001), (6, 'Fargo', 10, 5.0);
        """
    )
    con.commit()
    con.close()
    return database_runner(f"sqlite:///{path}")


def item(item_id: str, sql: str | None, *, ordered: bool = False, question: str = "") -> GoldItem:
    if sql is None:
        return GoldItem(
            id=item_id,
            category="out_of_schema",
            difficulty="easy",
            features=[],
            question=question or f"Question {item_id} about something we do not hold?",
            gold_sql=None,
            ordered=False,
            refusal_reason="not held",
        )
    return GoldItem(
        id=item_id,
        category="in_schema",
        difficulty="easy",
        features=[],
        question=question or f"Question {item_id} about cities?",
        gold_sql=sql,
        ordered=ordered,
        refusal_reason=None,
    )


def checks(items: list[GoldItem], runner: Any, counts: dict[str, int] | None = None) -> list[str]:
    return [f"{p.item_id}:{p.check}" for p in check_items(items, runner, SEEN, counts)]


def test_order_items_reads_only_the_outer_order_by() -> None:
    sql = (
        "SELECT c.name, (SELECT max(x) FROM t ORDER BY x DESC LIMIT 1) AS m, count(*) AS n "
        "FROM c GROUP BY c.name ORDER BY n DESC NULLS LAST, c.name ASC LIMIT 5"
    )
    assert order_items(sql) == ["n", "c.name"]
    assert order_items("SELECT 1") == []
    assert order_items("SELECT a FROM t ORDER BY 'x,y', a;") == ["'x,y'", "a"]


def test_outer_limit_and_raising_it_ignore_subqueries() -> None:
    sql = "SELECT a FROM t WHERE a > (SELECT b FROM u LIMIT 1) ORDER BY a LIMIT 10"
    assert outer_limit(sql) == 10
    assert with_limit(sql, 11).endswith("LIMIT 11")
    assert "LIMIT 1)" in with_limit(sql, 11)
    assert outer_limit("SELECT a FROM t") is None
    with pytest.raises(ValueError, match="no outer LIMIT"):
        with_limit("SELECT a FROM t", 3)


def test_key_columns_by_name_qualified_name_and_position() -> None:
    columns = ["name", "jobs"]
    assert key_columns(["jobs", "c.name"], columns) == [1, 0]
    assert key_columns(["2"], columns) == [1]
    assert key_columns(["count(*)"], columns) == "count(*)"


def test_a_clean_item_passes(runner: Any) -> None:
    good = item("h3-001", "SELECT name, jobs FROM cities ORDER BY jobs DESC LIMIT 1", ordered=True)
    plain = item("h3-002", "SELECT count(*) FROM cities")
    assert checks([good, plain], runner) == []


def test_rows_that_tie_inside_the_answer_fail(runner: Any) -> None:
    tied = item("h3-001", "SELECT name, jobs FROM cities ORDER BY jobs DESC LIMIT 4", ordered=True)
    assert checks([tied], runner) == ["h3-001:ties"]


def test_a_tie_across_the_limit_fails(runner: Any) -> None:
    # Boise and Cary both have 40 jobs; LIMIT 2 keeps Akron and one of them.
    cut = item("h3-001", "SELECT name, jobs FROM cities ORDER BY jobs DESC LIMIT 2", ordered=True)
    assert checks([cut], runner) == ["h3-001:ties"]


def test_numbers_within_the_scorer_tolerance_tie(runner: Any) -> None:
    near = item(
        "h3-001", "SELECT name, revenue FROM cities ORDER BY revenue DESC LIMIT 1", ordered=True
    )
    assert checks([near], runner) == ["h3-001:ties"]


def test_a_tie_break_named_in_the_order_by_is_part_of_the_ordering(runner: Any) -> None:
    named = item(
        "h3-001",
        "SELECT name, jobs FROM cities ORDER BY jobs DESC, name LIMIT 4",
        ordered=True,
        question="Top 4 cities by jobs, ties alphabetically?",
    )
    assert checks([named], runner) == []


def test_an_order_by_on_a_column_not_returned_fails(runner: Any) -> None:
    hidden_key = item("h3-001", "SELECT name FROM cities ORDER BY jobs DESC LIMIT 1", ordered=True)
    assert checks([hidden_key], runner) == ["h3-001:ties"]


def test_sql_that_fails_or_returns_nothing_fails(runner: Any) -> None:
    broken = item("h3-001", "SELECT nope FROM cities")
    empty = item("h3-002", "SELECT name FROM cities WHERE jobs > 1000")
    assert checks([broken, empty], runner) == ["h3-001:runs", "h3-002:runs"]


def test_two_runs_that_differ_fail() -> None:
    calls: list[int] = []

    def flaky(sql: str) -> tuple[list[str], list[tuple[Any, ...]]]:
        calls.append(1)
        return ["n"], [(len(calls),)]

    assert checks([item("h3-001", "SELECT n")], flaky) == ["h3-001:runs"]


def test_a_shared_six_word_run_with_a_seen_question_fails(runner: Any) -> None:
    close = item(
        "h3-001", "SELECT count(*) FROM cities", question="So how many invoices are still unpaid?"
    )
    far = item("h3-002", "SELECT count(*) FROM cities", question="How many invoices are paid?")
    found = checks([close, far], runner)
    assert found == ["h3-001:overlap", "h3-002:duplicate_sql"]
    assert "how many invoices are still unpaid" in word_runs(close.question)


def test_duplicate_ids_and_wrong_counts_fail(runner: Any) -> None:
    a = item("h3-001", "SELECT count(*) FROM cities")
    b = item("h3-001", None)
    found = checks([a, b], runner, {"in_schema": 1, "out_of_schema": 2, "should_refuse": 0})
    assert found == ["h3-001:ids", "*:counts"]
