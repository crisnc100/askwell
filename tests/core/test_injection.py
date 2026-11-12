"""Injection fixtures: hostile values run as bound parameters and change nothing; hostile
names never resolve; odd real identifiers are quoted. The DB content hash is checked
before and after on both engines."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import Engine, create_engine, text

from askwell.core.executor import readonly_engine, run
from askwell.core.intent import Intent
from askwell.core.registry import EntityDef, FieldDef, Registry
from askwell.core.sqlbuild import build, compile_sql
from askwell.core.validate import validate
from askwell.fieldservice.seed import content_hash
from tests.core.conftest import NOW

PAYLOADS = [
    "'; DROP TABLE parts; --",
    "x' OR '1'='1",
    '"; DELETE FROM invoices; --',
    "1; UPDATE technicians SET hourly_rate = 0",
    "%' UNION SELECT password_hash FROM users --",
    "Robert'); DROP TABLE work_orders;--",
    "\\'; TRUNCATE customers; --",
    "') OR 1=1; COMMIT; DROP TABLE sites; --",
]


def _intents(payload: str) -> list[dict[str, Any]]:
    return [
        {
            "intent_type": "row_list",
            "entity": "customers",
            "select": ["name"],
            "filters": [{"field": "name", "op": "eq", "value": payload}],
        },
        {
            "intent_type": "row_list",
            "entity": "parts",
            "select": ["sku"],
            "filters": [{"field": "name", "op": "ilike_contains", "value": payload}],
        },
        {
            "intent_type": "summary",
            "entity": "work_orders",
            "metrics": [{"agg": "count"}],
            "filters": [{"field": "customers.name", "op": "in", "values": [payload, "x"]}],
        },
        {
            "intent_type": "summary",
            "entity": "invoices",
            "metrics": [{"agg": "count"}],
            "filters": [
                {
                    "any_of": [
                        {"field": "technicians.full_name", "op": "neq", "value": payload},
                        {"field": "sites.name", "op": "eq", "value": payload},
                    ]
                }
            ],
        },
    ]


@pytest.mark.parametrize("engine_name", ["postgresql", "sqlite"])
def test_hostile_values_change_nothing(
    engine_name: str,
    registry: Registry,
    pg_seeded: Engine,
    pg_owner: Engine,
    sqlite_ro: Engine,
    sqlite_fieldservice: Engine,
) -> None:
    engine, owner = (
        (pg_seeded, pg_owner) if engine_name == "postgresql" else (sqlite_ro, sqlite_fieldservice)
    )
    before = content_hash(owner)
    executed = 0
    for payload in PAYLOADS:
        for raw in _intents(payload):
            result = validate(Intent.model_validate(raw), registry, now=NOW)
            assert result.plan is not None, result.issues
            stmt = build(result.plan)
            sql, _ = compile_sql(stmt, engine_name)
            assert payload not in sql
            run(engine, stmt)
            executed += 1
    assert executed == len(PAYLOADS) * 4
    assert content_hash(owner) == before


@pytest.mark.parametrize(
    "intent",
    [
        {"intent_type": "row_list", "entity": "parts; DROP TABLE parts", "select": ["name"]},
        {"intent_type": "row_list", "entity": "parts", "select": ["name FROM users --"]},
        {
            "intent_type": "row_list",
            "entity": "parts",
            "select": ["name"],
            "order_by": [{"target": "1; DROP TABLE parts"}],
        },
        {
            "intent_type": "summary",
            "entity": "parts",
            "metrics": [{"agg": "sum", "field": "unit_price) FROM parts; --"}],
        },
        {
            "intent_type": "grouped_summary",
            "entity": "parts",
            "metrics": [{"agg": "count"}],
            "group_by": [{"field": "pg_catalog.pg_user.passwd"}],
        },
    ],
)
def test_hostile_names_never_resolve(registry: Registry, intent: dict[str, Any]) -> None:
    result = validate(Intent.model_validate(intent), registry, now=NOW)
    assert result.plan is None
    assert set(result.codes) <= {"unknown_entity", "unknown_field"}
    assert result.codes


def test_odd_real_identifiers_are_quoted(tmp_path: Path) -> None:
    path = tmp_path / "odd.sqlite"
    writer = create_engine(f"sqlite:///{path}")
    with writer.begin() as conn:
        conn.execute(
            text(
                'CREATE TABLE "Order Lines" ("Line.ID" INTEGER, "Unit Price" REAL, '
                '"select" TEXT, "a""b" TEXT)'
            )
        )
        conn.execute(
            text("INSERT INTO \"Order Lines\" VALUES (1, 2.5, 'x', 'q'), (2, 4.0, 'y', 'q')")
        )
    writer.dispose()
    registry = Registry(
        schema_version=1,
        draft=False,
        entities={
            "order_lines": EntityDef(
                table="Order Lines",
                fields={
                    "line_id": FieldDef(column="Line.ID", type="integer"),
                    "unit_price": FieldDef(column="Unit Price", type="number", aggregatable=True),
                    "select": FieldDef(column="select", type="text"),
                    "a_b": FieldDef(column='a"b', type="text"),
                },
            )
        },
    )
    intent = Intent.model_validate(
        {
            "intent_type": "grouped_summary",
            "entity": "order_lines",
            "metrics": [{"agg": "sum", "field": "unit_price"}],
            "group_by": [{"field": "a_b"}],
            "filters": [{"field": "select", "op": "in", "values": ["x", "y"]}],
        }
    )
    plan = validate(intent, registry, now=NOW).plan
    assert plan is not None
    engine = readonly_engine(f"sqlite:///{path}")
    try:
        assert run(engine, build(plan)).rows == [("q", 6.5)]
    finally:
        engine.dispose()
