"""A file with no ID column loads with its rows numbered (Cristian's O11 decision,
2026-11-14): a hidden generated key, and a gentle note instead of an error. Nothing can
link to it until it has an ID column of its own."""

from __future__ import annotations

from pathlib import Path

from askwell.core.executor import readonly_engine, run
from askwell.core.intent import Intent
from askwell.core.registry import load_registry
from askwell.core.sqlbuild import build
from askwell.core.validate import validate
from askwell.workspace import fields
from askwell.workspace.check import ROW_KEY, check_files
from askwell.workspace.load import load_tables
from tests.core.conftest import NOW
from tests.workspace.conftest import csv_file

VISITS = csv_file("visits.csv", "city,minutes\nAvon,10\nAvon,15\nBrent,5\n")


def test_a_file_with_no_id_column_loads_with_a_note() -> None:
    result = check_files([VISITS])
    assert result.ok
    [report] = result.files
    [problem] = report.problems
    assert (problem.level, problem.code) == ("warning", "no_id_column")
    assert problem.message == "No id column found; rows are numbered for you"
    assert "id or visits_id" in problem.fix
    [plan] = result.tables
    assert plan.id_column == ROW_KEY
    assert [c.name for c in plan.columns] == [ROW_KEY, "city", "minutes"]
    assert [row[0] for row in plan.rows] == ["1", "2", "3"]


def test_the_row_key_is_hidden_and_the_table_answers(tmp_path: Path) -> None:
    result = check_files([VISITS])
    db = tmp_path / "w.sqlite"
    load_tables(result.tables, db)
    drafted = fields.draft(db, result.tables)
    (tmp_path / "draft.yaml").write_text(drafted[fields.DRAFT_FILE], encoding="utf-8")
    info = fields.FieldInfo.from_json(drafted[fields.FIELDS_FILE])
    registry = fields.apply(load_registry(tmp_path / "draft.yaml"), info, fields.Edits())
    entity = registry.entities["visits"]
    assert entity.primary_key == [ROW_KEY]
    assert entity.fields[ROW_KEY].hidden
    intent = Intent.model_validate(
        {
            "intent_type": "row_list",
            "entity": "visits",
            "select": ["city", "minutes"],
            "filters": [{"field": "city", "op": "eq", "value": "Avon"}],
        }
    )
    plan = validate(intent, registry, now=NOW).plan
    assert plan is not None
    engine = readonly_engine(f"sqlite:///{db}")
    try:
        assert run(engine, build(plan)).rows == [("Avon", 10), ("Avon", 15)]
    finally:
        engine.dispose()


def test_a_file_that_already_has_the_key_name_gets_another() -> None:
    clash = csv_file("logs.csv", f"{ROW_KEY},note\nx,a\ny,b\n")
    [plan] = check_files([clash]).tables
    assert plan.id_column == f"{ROW_KEY}_2"
    assert [c.name for c in plan.columns][:2] == [f"{ROW_KEY}_2", ROW_KEY]


def test_a_link_table_still_needs_no_key() -> None:
    result = check_files(
        [
            csv_file("customers.csv", "id,name\n1,a\n2,b\n"),
            csv_file("products.csv", "id,name\n1,x\n2,y\n"),
            csv_file("likes.csv", "customer_id,product_id\n1,2\n2,1\n"),
        ]
    )
    assert result.ok
    likes = next(t for t in result.tables if t.name == "likes")
    assert likes.id_column is None
    assert not [p for f in result.files for p in f.problems if p.code == "no_id_column"]
