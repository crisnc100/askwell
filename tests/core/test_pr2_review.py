"""PR-2 review fixes (review a13dba, f1-f8)."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import Engine

from askwell.bench.report import build as build_report
from askwell.bench.report import render_markdown
from askwell.bench.run import RunResult
from askwell.core.executor import readonly_engine
from askwell.core.features import ALL
from askwell.core.intent import Intent
from askwell.core.registry import (
    EntityDef,
    FieldDef,
    Registry,
    Relationship,
    dump_registry,
    load_registry,
)
from askwell.core.registry_init import init_registry
from askwell.core.sqlbuild import build
from askwell.core.validate import validate
from askwell.pipeline.prompt import registry_view
from askwell.workspace import fields
from askwell.workspace.check import check_files
from askwell.workspace.load import load_tables
from tests.core.conftest import NOW
from tests.core.dual import pg_db, sqlite_db
from tests.workspace.conftest import csv_file

NO_INFERENCE = ALL - {"inferred_links"}
KEYS = range(1, 13)


def _rows(name: str, values: list[str]) -> str:
    return f"INSERT INTO {name} VALUES " + ", ".join(values)


# --- f1: a link drawn only because inferred_links was on is not used when it is off ---

FLIGHTS = [
    "CREATE TABLE airlines (uid INTEGER PRIMARY KEY, name TEXT)",
    _rows("airlines", [f"({k}, 'line {k}')" for k in KEYS]),
    "CREATE TABLE flights (id INTEGER PRIMARY KEY, airline INTEGER)",
    _rows("flights", [f"({k}, {k})" for k in KEYS]),
]
BY_AIRLINE = {
    "intent_type": "grouped_summary",
    "entity": "flights",
    "metrics": [{"agg": "count"}],
    "group_by": [{"field": "airlines.name"}],
}


def _codes(registry: Registry, features: frozenset[str], intent: dict[str, Any]) -> list[str]:
    result = validate(
        Intent.model_validate(intent), registry, now=NOW, allow_draft=True, features=features
    )
    return result.codes


def test_a_link_drafted_with_inferred_links_is_marked(tmp_path: Path) -> None:
    with sqlite_db(tmp_path / "f.sqlite", FLIGHTS) as engine:
        registry = init_registry(engine).registry
    [rel] = registry.relationships
    assert rel.feature == "inferred_links"
    assert "feature: inferred_links" in dump_registry(registry)
    assert load_registry_text(dump_registry(registry)).relationships == [rel]


def test_switching_inferred_links_off_refuses_a_link_drafted_with_it_on(tmp_path: Path) -> None:
    with sqlite_db(tmp_path / "f.sqlite", FLIGHTS) as engine:
        registry = init_registry(engine).registry
        today = init_registry(engine, features=NO_INFERENCE).registry
    assert _codes(registry, ALL, BY_AIRLINE) == []
    assert _codes(registry, NO_INFERENCE, BY_AIRLINE) == _codes(today, NO_INFERENCE, BY_AIRLINE)
    assert _codes(registry, NO_INFERENCE, BY_AIRLINE) != []
    assert (
        "flights.airline -> airlines"
        not in registry_view(registry, NOW, 16000, features=NO_INFERENCE).text
    )


def test_older_inferred_links_need_no_switch(tmp_path: Path) -> None:
    statements = [
        "CREATE TABLE customers (id INTEGER PRIMARY KEY)",
        "CREATE TABLE orders (id INTEGER PRIMARY KEY, customer_id INTEGER)",
    ]
    with sqlite_db(tmp_path / "o.sqlite", statements) as engine:
        [rel] = init_registry(engine).registry.relationships
    assert rel.source == "inferred"
    assert rel.feature is None


def test_an_uploaded_named_link_is_marked(tmp_path: Path) -> None:
    airports = csv_file("airports.csv", "id,name\n" + "".join(f"{k},n{k}\n" for k in KEYS))
    flights = csv_file(
        "flights.csv", "id,origin_airport_id\n" + "".join(f"{k},{k}\n" for k in KEYS)
    )
    contacts = csv_file("contacts.csv", "id,airport_id\n" + "".join(f"{k},{k}\n" for k in KEYS))
    result = check_files([airports, flights, contacts])
    assert result.ok
    db = tmp_path / "w.sqlite"
    load_tables(result.tables, db)
    drafted = fields.draft(db, result.tables)
    registry = load_registry_text(drafted[fields.DRAFT_FILE])
    marks = {(r.from_entity, r.from_field): r.feature for r in registry.relationships}
    assert marks == {
        ("flights", "origin_airport_id"): "inferred_links",
        ("contacts", "airport_id"): None,
    }


def load_registry_text(text: str) -> Registry:
    import tempfile

    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as fh:
        fh.write(text)
    return load_registry(fh.name)


# --- f2: containment compares the cells conversion will read ---


def test_padded_link_values_do_not_adopt_a_link_that_would_fail_to_load() -> None:
    airports = csv_file("airports.csv", "id,name\n" + "".join(f"{k},n{k}\n" for k in KEYS))
    flights = csv_file(
        "flights.csv", "id,origin_airport_id\n" + "".join(f'{k}," {k}"\n' for k in KEYS)
    )
    off = check_files([airports, flights], features=NO_INFERENCE)
    on = check_files([airports, flights])
    assert off.ok
    assert on.ok, [p.code for f in on.files for p in f.problems]


# --- f3: two label keys reached by two named links stay apart ---


def test_grouping_by_two_named_links_to_a_labelled_entity_builds() -> None:
    registry = Registry(
        schema_version=1,
        draft=False,
        entities={
            "airports": EntityDef(
                table="airports",
                primary_key=["id"],
                label="city",
                fields={
                    "id": FieldDef(column="id", type="integer"),
                    "city": FieldDef(column="city", type="text"),
                },
            ),
            "flights": EntityDef(
                table="flights",
                primary_key=["id"],
                fields={
                    "id": FieldDef(column="id", type="integer"),
                    "origin_id": FieldDef(column="origin_id", type="integer"),
                    "dest_id": FieldDef(column="dest_id", type="integer"),
                },
            ),
        },
        relationships=[
            Relationship(
                from_entity="flights",
                from_field=f,
                to_entity="airports",
                to_field="id",
                source="declared",
            )
            for f in ("origin_id", "dest_id")
        ],
    )
    intent = {
        "intent_type": "grouped_summary",
        "entity": "flights",
        "metrics": [{"agg": "count", "alias": "n"}],
        "group_by": [{"field": "airports@origin_id.city"}, {"field": "airports@dest_id.city"}],
    }
    result = validate(Intent.model_validate(intent), registry, now=NOW)
    assert result.plan is not None, result.issues
    labels = [c.name for c in build(result.plan).selected_columns]
    assert len(labels) == len(set(labels))
    assert "airports_origin_id__id" in labels
    assert "airports_dest_id__id" in labels


# --- f4, f5: what reads as a number is what both engines cast ---


@pytest.mark.parametrize(
    ("label", "odd"),
    [("a tab-padded placeholder", "\tnull"), ("non-ASCII digits", "١٢")],
)
def test_a_column_the_cast_would_misread_stays_text(tmp_path: Path, label: str, odd: str) -> None:
    statements = [
        "CREATE TABLE t (id INTEGER PRIMARY KEY, amount TEXT)",
        _rows("t", [f"({k}, '{k}')" for k in range(1, 8)]),
    ]
    with sqlite_db(tmp_path / "n.sqlite", statements) as engine:
        assert init_registry(engine).registry.entities["t"].fields["amount"].text_number
    path = tmp_path / "odd.sqlite"
    with sqlite3.connect(path) as conn:
        for statement in statements:
            conn.execute(statement)
        conn.execute("INSERT INTO t VALUES (8, ?)", (odd,))
    engine = readonly_engine(f"sqlite:///{path}")
    try:
        amount = init_registry(engine).registry.entities["t"].fields["amount"]
    finally:
        engine.dispose()
    assert amount.type == "text", label
    assert not amount.text_number, label


# --- f6: a NULL key in the target does not hide missing values ---


def test_a_null_target_key_does_not_pass_containment(tmp_path: Path) -> None:
    statements = [
        "CREATE TABLE airlines (uid TEXT PRIMARY KEY, name TEXT)",
        "INSERT INTO airlines VALUES (NULL, 'none'), ('x', 'x')",
        "CREATE TABLE flights (id INTEGER PRIMARY KEY, airline TEXT)",
        _rows("flights", [f"({k}, 'a{k}')" for k in KEYS]),
    ]
    with sqlite_db(tmp_path / "n.sqlite", statements) as engine:
        result = init_registry(engine)
    assert result.registry.relationships == []


# --- f7: a text column named after a table with integer keys skips, never aborts ---


@pytest.fixture
def pg_text_link(pg_owner: Engine) -> Iterator[Engine]:
    statements = [
        "CREATE TABLE airlines (uid INTEGER PRIMARY KEY, name TEXT)",
        _rows("airlines", [f"({k}, 'line {k}')" for k in KEYS]),
        "CREATE TABLE flights (id INTEGER PRIMARY KEY, airline TEXT)",
        _rows("flights", [f"({k}, '{k}')" for k in KEYS]),
    ]
    with pg_db(pg_owner, "askwell_test_textlink", statements) as engine:
        yield engine


def test_a_type_mismatched_candidate_is_skipped_on_postgres(pg_text_link: Engine) -> None:
    result = init_registry(pg_text_link)
    assert result.registry.relationships == []
    assert sorted(result.registry.entities) == ["airlines", "flights"]


# --- f8: the CSV report lists every table that failed to load ---


def test_the_report_lists_load_failures_no_question_touched() -> None:
    result = RunResult(
        run_id="t",
        records=[],
        systems=["askwell_csv"],
        models=["m"],
        csv_load_failures={"spider_x": {"unused": ["no_id_column"]}},
    )
    report = build_report(result)
    assert report["csv_load_failures"] == {"spider_x": {"unused": ["no_id_column"]}}
    assert "- spider_x: `unused`: no_id_column" in render_markdown(report)
