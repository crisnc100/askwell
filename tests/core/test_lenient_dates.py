"""A column declared DATE/DATETIME may hold values that are not dates (Spider's wta_1 stores
birth dates as integers like 19800930). Reading them must not crash the query: values that
parse come back as dates, others come back as stored."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from sqlalchemy import create_engine, text

from ledgerline.core.executor import readonly_engine, run
from ledgerline.core.intent import Intent
from ledgerline.core.registry import EntityDef, FieldDef, Registry
from ledgerline.core.sqlbuild import build
from ledgerline.core.validate import validate
from tests.core.conftest import NOW


def test_non_date_values_in_date_columns_come_back_as_stored(tmp_path: Path) -> None:
    path = tmp_path / "odd.sqlite"
    writer = create_engine(f"sqlite:///{path}")
    with writer.begin() as conn:
        conn.execute(text("CREATE TABLE p (id INTEGER PRIMARY KEY, born DATE, seen DATETIME)"))
        conn.execute(
            text(
                "INSERT INTO p VALUES (1, 19800930, 'not a time'), "
                "(2, '1982-03-09', '2026-01-02 03:04:05.000000'), (3, NULL, NULL)"
            )
        )
    writer.dispose()
    registry = Registry(
        schema_version=1,
        draft=False,
        entities={
            "p": EntityDef(
                table="p",
                fields={
                    "id": FieldDef(column="id", type="integer"),
                    "born": FieldDef(column="born", type="date"),
                    "seen": FieldDef(column="seen", type="datetime"),
                },
            )
        },
    )
    intent = Intent.model_validate(
        {
            "intent_type": "row_list",
            "entity": "p",
            "select": ["id", "born", "seen"],
            "order_by": [{"target": "id"}],
        }
    )
    plan = validate(intent, registry, now=NOW).plan
    assert plan is not None
    engine = readonly_engine(f"sqlite:///{path}")
    try:
        rows = run(engine, build(plan)).rows
    finally:
        engine.dispose()
    assert rows == [
        (1, 19800930, "not a time"),
        (2, date(1982, 3, 9), datetime(2026, 1, 2, 3, 4, 5)),
        (3, None, None),
    ]
