"""P3.1: the 9 seen v0.2 held-out refusals in scope and the 13 seen Spider "has none"
and aggregate-comparison refusals, each written by hand as a grammar v0.3 intent and
checked against the gold rows. Expressibility only, not accuracy.

Held-out golds run on the seeded fieldservice Postgres, the intents on Postgres and
SQLite. Spider text stays out of the repository: an intent's `$n` is the n-th quoted
value of the item's gold SQL, read from the local Spider copy at test time."""

from __future__ import annotations

import json
import re
import shutil
import sqlite3
from functools import cache
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import Engine, text

from askwell.bench.compare import results_match
from askwell.bench.items import ROOT, EvalItem, spider_items
from askwell.bench.spider import db_path, generate
from askwell.bench.systems import raw_sql
from askwell.core.executor import readonly_engine, run
from askwell.core.intent import Intent
from askwell.core.registry import Registry
from askwell.core.sqlbuild import build
from askwell.core.validate import validate
from tests.core.conftest import NOW

ROW_CAP = 1000
COUNT = [{"agg": "count"}]
OPEN = ["open", "scheduled", "in_progress"]


def _eq(field: str, value: Any) -> dict[str, Any]:
    return {"field": field, "op": "eq", "value": value}


HOLDOUT: dict[str, dict[str, Any]] = {
    "ho-011": {
        "intent_type": "grouped_summary",
        "entity": "work_orders",
        "metrics": [{"agg": "avg", "field": {"days_between": ["opened_at", "completed_at"]}}],
        "group_by": [{"field": "job_type"}],
        "filters": [_eq("status", "completed")],
        "date_range": {"field": "completed_at", "start": "2025-06-30", "end": "2026-06-30"},
    },
    "ho-012": {
        "intent_type": "grouped_summary",
        "entity": "invoices",
        "metrics": [{"agg": "avg", "field": {"days_between": ["issued_at", "paid_at"]}}],
        "group_by": [{"field": "customers.segment"}],
        "filters": [_eq("status", "paid")],
        "date_range": {"field": "issued_at", "start": "2025-01-01", "end": "2026-01-01"},
    },
    "ho-013": {
        "intent_type": "summary",
        "entity": "work_order_parts",
        "metrics": [
            {
                "agg": "sum",
                "field": {"op": "multiply", "left": "quantity", "right": "parts.unit_cost"},
            }
        ],
        "filters": [_eq("work_orders.status", "completed")],
        "date_range": {
            "field": "work_orders.completed_at",
            "start": "2026-05-01",
            "end": "2026-06-01",
        },
    },
    "ho-015": {
        "intent_type": "row_list",
        "entity": "work_orders",
        "select": ["id"],
        "filters": [_eq("status", "completed"), {"has": "invoices", "none": True}],
    },
    "ho-016": {
        "intent_type": "summary",
        "entity": "customers",
        "metrics": COUNT,
        "filters": [
            _eq("is_active", True),
            {
                "has": "work_orders",
                "none": True,
                "where": [{"field": "opened_at", "op": "gte", "value": "2026-04-01"}],
            },
        ],
    },
    "ho-018": {
        "intent_type": "grouped_summary",
        "entity": "work_orders",
        "metrics": [
            {
                "agg": "sum",
                "alias": "labor_value",
                "field": {
                    "op": "multiply",
                    "left": "labor_hours",
                    "right": "technicians.hourly_rate",
                },
            }
        ],
        "group_by": [{"field": "technicians.full_name"}],
        "filters": [_eq("status", "completed")],
        "date_range": {"field": "completed_at", "start": "2026-05-01", "end": "2026-06-01"},
        "order_by": [{"target": "labor_value", "direction": "desc"}],
        "limit": 5,
    },
    "ho-019": {
        "intent_type": "row_list",
        "entity": "work_orders",
        "select": ["id", "status", {"days_between": ["opened_at", "now"], "alias": "days_open"}],
        "filters": [{"field": "status", "op": "in", "values": OPEN}],
        "order_by": [{"target": "opened_at"}],
        "limit": 10,
    },
    "ho-025": {
        "intent_type": "row_list",
        "entity": "technicians",
        "select": ["id", "full_name", "hourly_rate"],
        "filters": [{"field": "hourly_rate", "op": "gt", "value": {"of": "avg"}}],
    },
}

HOLDOUT_NOT_EXPRESSIBLE = {
    "ho-014": "markup is quantity times (price minus cost): three fields, and a computed "
    "value takes two",
}

SPIDER: dict[str, tuple[str, dict[str, Any]]] = {
    # has / has none
    "spider:920": (
        "dogs",
        {
            "intent_type": "summary",
            "metrics": [{"agg": "avg", "field": "age"}],
            "filters": [{"has": "treatments"}],
        },
    ),
    "spider:978": (
        "dogs",
        {
            "intent_type": "summary",
            "metrics": COUNT,
            "filters": [{"has": "treatments", "none": True}],
        },
    ),
    "spider:257": (
        "airports",
        {
            "intent_type": "row_list",
            "select": ["airportname"],
            "filters": [
                {"has": "flights@sourceairport", "none": True},
                {"has": "flights@destairport", "none": True},
            ],
        },
    ),
    "spider:914": (
        "highschooler",
        {
            "intent_type": "summary",
            "metrics": [{"agg": "avg", "field": "grade"}],
            "filters": [{"has": "friend@student_id"}],
        },
    ),
    "spider:915": (
        "highschooler",
        {
            "intent_type": "summary",
            "metrics": [{"agg": "avg", "field": "grade"}],
            "filters": [{"has": "friend@student_id"}],
        },
    ),
    # comparison with an aggregate
    "spider:101": (
        "cars_data",
        {
            "intent_type": "row_list",
            "select": ["car_names.make", "year"],
            "filters": [{"field": "year", "op": "eq", "value": {"of": "min"}}],
        },
    ),
    "spider:974": (
        "dogs",
        {
            "intent_type": "summary",
            "metrics": COUNT,
            "filters": [{"field": "age", "op": "lt", "value": {"of": "avg"}}],
        },
    ),
}

SPIDER_NOT_EXPRESSIBLE = {
    "spider:924": "dogs whose treatments total over 1000: a has-none on a sum of related rows",
    "spider:925": "dogs whose treatments total over 1000: a has-none on a sum of related rows",
    "spider:167": "the gold's minimum is over all cars, the question's rows are the cars "
    "with 3 or fewer cylinders: the aggregate's rows differ from the question's (item 4)",
    "spider:168": "the gold's minimum is over all cars, the question's rows are the cars "
    "with fewer than 4 cylinders: the aggregate's rows differ from the question's (item 4)",
    "spider:944": "professionals with a treatment below the average treatment cost: the "
    "aggregate is of another entity's field (item 4)",
    "spider:945": "professionals with a treatment below the average treatment cost: the "
    "aggregate is of another entity's field (item 4)",
}

SPIDER_DATABASES = ["car_1", "dog_kennels", "flight_2", "network_1"]
_QUOTED = re.compile(r"'([^']*)'|\"([^\"]*)\"")
# flight_2's airport codes carry a leading space in flights (see test_expressible_v03).
TRIM = [
    "UPDATE flights SET SourceAirport = trim(SourceAirport), DestAirport = trim(DestAirport)",
    "UPDATE airports SET City = trim(City)",
]


@cache
def _holdout() -> dict[str, dict[str, Any]]:
    path = ROOT / "evals" / "gold" / "holdout-v02.jsonl"
    return {d["id"]: d for d in map(json.loads, path.read_text().splitlines()) if d}


@cache
def _spider() -> dict[str, tuple[str, EvalItem]]:
    return {i.id: (db, i) for db in SPIDER_DATABASES for i in spider_items(db)}


@cache
def _spider_registry(db_id: str) -> Registry:
    import yaml

    return Registry.model_validate(yaml.safe_load(generate(db_id)))


def test_the_items_are_the_plans_22() -> None:
    assert len(HOLDOUT) + len(HOLDOUT_NOT_EXPRESSIBLE) == 9
    assert len(SPIDER) + len(SPIDER_NOT_EXPRESSIBLE) == 13
    assert not set(HOLDOUT) & set(HOLDOUT_NOT_EXPRESSIBLE)
    assert not set(SPIDER) & set(SPIDER_NOT_EXPRESSIBLE)


@pytest.mark.parametrize("engine_name", ["postgresql", "sqlite"])
@pytest.mark.parametrize("item_id", sorted(HOLDOUT))
def test_holdout_intent_returns_the_gold_rows(
    item_id: str, engine_name: str, registry: Registry, pg_seeded: Engine, sqlite_ro: Engine
) -> None:
    item = _holdout()[item_id]
    result = validate(Intent.model_validate(HOLDOUT[item_id]), registry, now=NOW)
    assert result.plan is not None, result.issues
    with pg_seeded.connect() as conn:
        gold = conn.execute(text(item["gold_sql"])).fetchall()
    assert gold
    engine = pg_seeded if engine_name == "postgresql" else sqlite_ro
    got = run(engine, build(result.plan), row_cap=ROW_CAP).rows
    assert results_match(got, gold, ordered=bool(item.get("ordered"))), (got[:5], gold[:5])


@pytest.fixture(scope="module")
def spider_paths(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    paths = {db: db_path(db) for db in SPIDER_DATABASES}
    trimmed = tmp_path_factory.mktemp("spider") / "flight_2.sqlite"
    shutil.copyfile(paths["flight_2"], trimmed)
    with sqlite3.connect(trimmed) as conn:
        for statement in TRIM:
            conn.execute(statement)
    paths["flight_2"] = trimmed
    return paths


@pytest.mark.parametrize("item_id", sorted(SPIDER))
def test_spider_intent_returns_the_gold_rows(item_id: str, spider_paths: dict[str, Path]) -> None:
    db, item = _spider()[item_id]
    assert item.gold_sql is not None
    literals = [a or b for a, b in _QUOTED.findall(item.gold_sql)]
    entity, body = SPIDER[item_id]
    intent = json.loads(
        re.sub(
            r'"\$(\d+)"',
            lambda m: json.dumps(literals[int(m.group(1)) - 1]),
            json.dumps({"entity": entity, **body}),
        )
    )
    result = validate(
        Intent.model_validate(intent), _spider_registry(db), now=NOW, allow_draft=True
    )
    assert result.plan is not None, result.issues
    engine = readonly_engine(f"sqlite:///{spider_paths[db]}")
    try:
        got = run(engine, build(result.plan), row_cap=ROW_CAP).rows
        gold = run(engine, raw_sql(item.gold_sql), row_cap=ROW_CAP).rows
    finally:
        engine.dispose()
    # Every flight_2 airport has a flight, so its "no flights" gold is rightly empty.
    assert bool(gold) != (item_id == "spider:257")
    assert results_match(got, gold, ordered=item.ordered, row_cap=ROW_CAP), (got[:5], gold[:5])
