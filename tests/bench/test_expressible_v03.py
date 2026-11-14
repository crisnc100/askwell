"""P2.1: the 62 seen Spider questions refused for two links, a missed link or numbers
stored as text, each written by hand as an intent and checked against the gold rows.
Expressibility only: whether PR-2's registry and grammar can say the question, not
whether a model will.

Spider text stays out of the repository: an intent's `$n` is the n-th quoted value in
the item's gold SQL, read from the local Spider copy at test time."""

from __future__ import annotations

import re
import shutil
import sqlite3
from functools import cache
from pathlib import Path
from typing import Any

import pytest
import yaml

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
COUNT = [{"agg": "count", "alias": "n"}]


def _count(**more: Any) -> dict[str, Any]:
    return {"intent_type": "summary", "metrics": COUNT, **more}


def _top(group: str, direction: str = "desc", **more: Any) -> dict[str, Any]:
    return {
        "intent_type": "grouped_summary",
        "metrics": COUNT,
        "group_by": [{"field": group}],
        "order_by": [{"target": "n", "direction": direction}],
        "limit": 1,
        **more,
    }


def _per(group: str, **more: Any) -> dict[str, Any]:
    return {
        "intent_type": "grouped_summary",
        "metrics": COUNT,
        "group_by": [{"field": group}],
        **more,
    }


def _eq(field: str, value: Any) -> dict[str, Any]:
    return {"field": field, "op": "eq", "value": value}


FRIEND = "highschooler@student_id.name"
SRC_CITY = "airports@sourceairport.city"
DEST_CITY = "airports@destairport.city"
LOWEST_HP = {
    "intent_type": "row_list",
    "select": ["car_names.model"],
    "order_by": [{"target": "horsepower"}],
    "limit": 1,
}

# item id -> (entity, intent without its entity)
INTENTS: dict[str, tuple[str, dict[str, Any]]] = {
    # car_1: numbers stored as text
    "spider:117": (
        "cars_data",
        {
            "intent_type": "summary",
            "metrics": [{"agg": "avg", "field": "mpg"}],
            "filters": [_eq("cylinders", 4)],
        },
    ),
    "spider:126": (
        "cars_data",
        _count(filters=[{"field": "horsepower", "op": "gt", "value": 150}]),
    ),
    "spider:132": (
        "cars_data",
        {
            "intent_type": "row_list",
            "select": ["horsepower", "car_names.make"],
            "filters": [_eq("cylinders", 3)],
            "order_by": [{"target": "horsepower", "direction": "desc"}],
            "limit": 1,
        },
    ),
    "spider:135": (
        "cars_data",
        {
            "intent_type": "summary",
            "metrics": [{"agg": "avg", "field": "horsepower"}],
            "filters": [{"field": "year", "op": "lt", "value": 1980}],
        },
    ),
    "spider:136": (
        "cars_data",
        {
            "intent_type": "summary",
            "metrics": [{"agg": "avg", "field": "horsepower"}],
            "filters": [{"field": "year", "op": "lt", "value": 1980}],
        },
    ),
    "spider:165": (
        "cars_data",
        {
            "intent_type": "row_list",
            "select": ["car_names.model"],
            "filters": [_eq("cylinders", 4)],
            "order_by": [{"target": "horsepower", "direction": "desc"}],
            "limit": 1,
        },
    ),
    "spider:170": (
        "cars_data",
        {
            "intent_type": "summary",
            "metrics": [{"agg": "max", "field": "mpg"}],
            "filters": [
                {
                    "any_of": [
                        _eq("cylinders", 8),
                        {"field": "year", "op": "lt", "value": 1980},
                    ]
                }
            ],
        },
    ),
    "spider:95": ("cars_data", LOWEST_HP),
    "spider:96": ("cars_data", LOWEST_HP),
    # car_1: the declared key to model_list's unique model column
    "spider:152": (
        "cars_data",
        _per(
            "model_list.model",
            filters=[
                {
                    "any_of": [
                        _eq("car_makers.fullname", "$1"),
                        {"field": "weight", "op": "gt", "value": 3500},
                    ]
                }
            ],
        ),
    ),
    "spider:171": (
        "cars_data",
        _per(
            "model_list.model",
            filters=[
                {"field": "weight", "op": "lt", "value": 3500},
                {"field": "car_makers.fullname", "op": "neq", "value": "$1"},
            ],
        ),
    ),
    "spider:172": (
        "cars_data",
        _per(
            "model_list.model",
            filters=[
                {"field": "weight", "op": "lt", "value": 3500},
                {"field": "car_makers.fullname", "op": "neq", "value": "$1"},
            ],
        ),
    ),
    # dog_kennels: numbers stored as text
    "spider:987": (
        "dogs",
        {"intent_type": "summary", "metrics": [{"agg": "avg", "field": "age"}]},
    ),
    # flight_2: two links to airports
    "spider:207": ("flights", _count(filters=[_eq(SRC_CITY, "$1")])),
    "spider:208": ("flights", _count(filters=[_eq(SRC_CITY, "$1")])),
    "spider:209": ("flights", _count(filters=[_eq(DEST_CITY, "$1")])),
    "spider:210": ("flights", _count(filters=[_eq(DEST_CITY, "$1")])),
    "spider:224": ("flights", _top(SRC_CITY)),
    "spider:251": (
        "flights",
        {"intent_type": "row_list", "select": ["flightno"], "filters": [_eq(SRC_CITY, "$1")]},
    ),
    "spider:252": (
        "flights",
        {"intent_type": "row_list", "select": ["flightno"], "filters": [_eq(SRC_CITY, "$1")]},
    ),
    "spider:254": (
        "flights",
        {"intent_type": "row_list", "select": ["flightno"], "filters": [_eq(DEST_CITY, "$1")]},
    ),
    "spider:255": (
        "flights",
        _count(filters=[{"field": DEST_CITY, "op": "in", "values": ["$1", "$2"]}]),
    ),
    # flight_2: flights.airline, inferred to airlines
    "spider:214": ("flights", _count(filters=[_eq("airlines.airline", "$1")])),
    "spider:215": (
        "flights",
        _count(filters=[_eq("airlines.airline", "$1"), _eq("destairport", "$2")]),
    ),
    "spider:216": (
        "flights",
        _count(filters=[_eq("airlines.airline", "$1"), _eq("destairport", "$2")]),
    ),
    "spider:217": (
        "flights",
        _count(filters=[_eq("airlines.airline", "$1"), _eq("sourceairport", "$2")]),
    ),
    "spider:218": (
        "flights",
        _count(filters=[_eq("airlines.airline", "$1"), _eq("sourceairport", "$2")]),
    ),
    "spider:219": (
        "flights",
        _count(filters=[_eq(DEST_CITY, "$1"), _eq("airlines.airline", "$2")]),
    ),
    "spider:220": (
        "flights",
        _count(filters=[_eq(DEST_CITY, "$1"), _eq("airlines.airline", "$2")]),
    ),
    "spider:229": ("flights", _top("airlines.airline")),
    "spider:230": ("flights", _top("airlines.airline")),
    "spider:231": (
        "flights",
        {
            "intent_type": "grouped_summary",
            "metrics": COUNT,
            "group_by": [
                {"field": "airlines.abbreviation"},
                {"field": "airlines.country"},
                {"field": "airlines.airline"},
            ],
            "order_by": [{"target": "n"}],
            "limit": 1,
        },
    ),
    "spider:233": (
        "flights",
        {
            "intent_type": "row_list",
            "select": ["airlines.airline"],
            "filters": [_eq("sourceairport", "$1")],
        },
    ),
    "spider:245": (
        "flights",
        {
            "intent_type": "row_list",
            "select": ["flightno"],
            "filters": [_eq("airlines.airline", "$1")],
        },
    ),
    "spider:246": (
        "flights",
        {
            "intent_type": "row_list",
            "select": ["flightno"],
            "filters": [_eq("airlines.airline", "$1")],
        },
    ),
    # network_1: two links to highschooler, from friend and from likes
    "spider:885": ("friend", _per(FRIEND)),
    "spider:886": ("friend", _top(FRIEND)),
    "spider:887": ("friend", _top(FRIEND)),
    "spider:889": ("friend", _per(FRIEND, having=[{"metric": "n", "op": "gte", "value": 3}])),
    "spider:890": (
        "friend",
        {
            "intent_type": "row_list",
            "select": ["highschooler@friend_id.name"],
            "filters": [_eq(FRIEND, "$1")],
        },
    ),
    "spider:891": (
        "friend",
        {
            "intent_type": "row_list",
            "select": ["highschooler@friend_id.name"],
            "filters": [_eq(FRIEND, "$1")],
        },
    ),
    "spider:892": ("friend", _count(filters=[_eq(FRIEND, "$1")])),
    "spider:893": ("friend", _count(filters=[_eq(FRIEND, "$1")])),
    "spider:904": ("likes", _per(FRIEND)),
    "spider:905": ("likes", _per(FRIEND)),
    "spider:906": ("likes", _top(FRIEND)),
    "spider:907": ("likes", _top(FRIEND)),
    "spider:908": ("likes", _per(FRIEND, having=[{"metric": "n", "op": "gte", "value": 2}])),
    "spider:909": ("likes", _per(FRIEND, having=[{"metric": "n", "op": "gte", "value": 2}])),
    "spider:910": (
        "friend",
        _per(
            FRIEND,
            filters=[{"field": "highschooler@student_id.grade", "op": "gt", "value": 5}],
            having=[{"metric": "n", "op": "gte", "value": 2}],
        ),
    ),
    "spider:911": (
        "friend",
        _per(
            FRIEND,
            filters=[{"field": "highschooler@student_id.grade", "op": "gt", "value": 5}],
            having=[{"metric": "n", "op": "gte", "value": 2}],
        ),
    ),
    "spider:912": ("likes", _count(filters=[_eq(FRIEND, "$1")])),
    "spider:913": ("likes", _count(filters=[_eq(FRIEND, "$1")])),
    # wta_1: two links to players
    "spider:488": (
        "matches",
        {
            "intent_type": "row_list",
            "select": [
                "players@winner_id.first_name",
                "players@winner_id.country_code",
                "players@winner_id.birth_date",
            ],
            "order_by": [{"target": "winner_rank_points", "direction": "desc"}],
            "limit": 1,
        },
    ),
}

# Triaged as two links, but the gold needs a set operation or rows with no related rows,
# which PR-2 does not add ("has none" is PR-3; set operations stay out).
NOT_EXPRESSIBLE: dict[str, str] = {
    "spider:258": "airports with no flight either way: has none",
    "spider:894": "students with no friend: has none",
    "spider:896": "students with no friend: has none",
    "spider:897": "students with no friend: has none",
    "spider:898": "has a friend and is liked: set intersection",
    "spider:900": "has a friend and is liked: set intersection",
    "spider:917": "lowest grade of students with no friend: has none",
    "spider:451": "won both of two tournaments: set intersection",
}

# Written and answered, but the gold rows differ for a reason in the gold itself.
TEXT_GOLD = (
    "the gold computes on the text: 'null' counts as 0 in avg, sorts above every number "
    "in max, and comparisons and ordering are by characters, not by value"
)
GOLD_DIFFERS: dict[str, str] = {
    **dict.fromkeys(
        ["spider:95", "spider:96", "spider:117", "spider:126", "spider:132"], TEXT_GOLD
    ),
    **dict.fromkeys(["spider:135", "spider:136", "spider:165", "spider:170"], TEXT_GOLD),
    "spider:152": "the gold's inner join drops a model whose maker is missing; ours keeps it "
    "when its weight qualifies",
    "spider:229": "every airline ties at the top; the gold's pick among them is arbitrary",
    "spider:230": "every airline ties at the top; the gold's pick among them is arbitrary",
}

TRIAGE_PREFIXES = (
    "Two foreign keys link the same pair",
    "Registry gap",
    "The column is declared TEXT but holds numbers",
)
DATABASES = ["car_1", "dog_kennels", "flight_2", "network_1", "wta_1"]
_QUOTED = re.compile(r"'([^']*)'|\"([^\"]*)\"")


@cache
def _registry(db_id: str) -> Registry:
    return Registry.model_validate(yaml.safe_load(generate(db_id)))


@cache
def _items() -> dict[str, tuple[str, EvalItem]]:
    return {item.id: (db, item) for db in DATABASES for item in spider_items(db)}


def _fill(value: Any, literals: list[str]) -> Any:
    if isinstance(value, str) and re.fullmatch(r"\$\d+", value):
        return literals[int(value[1:]) - 1]
    if isinstance(value, list):
        return [_fill(v, literals) for v in value]  # pyright: ignore[reportUnknownVariableType]
    if isinstance(value, dict):
        return {k: _fill(v, literals) for k, v in value.items()}  # pyright: ignore[reportUnknownVariableType]
    return value


def test_the_items_are_the_triaged_refusals() -> None:
    triaged: set[str] = set()
    for db in DATABASES:
        triage = yaml.safe_load((ROOT / "evals" / "triage" / f"spider_{db}.yaml").read_text())
        triaged |= {k for k, v in triage.items() if str(v["note"]).startswith(TRIAGE_PREFIXES)}
    assert len(triaged) == 62
    assert set(INTENTS) | set(NOT_EXPRESSIBLE) == triaged
    assert not set(INTENTS) & set(NOT_EXPRESSIBLE)


# flight_2 stores its airport codes in flights with a leading space and its cities with a
# trailing one, so every join or filter on them matches nothing, for the gold and for us
# alike: zero against zero says nothing. Both run on a copy with the spaces trimmed.
TRIM = [
    "UPDATE flights SET SourceAirport = trim(SourceAirport), DestAirport = trim(DestAirport)",
    "UPDATE airports SET City = trim(City)",
]


@pytest.fixture(scope="module")
def databases(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    paths = {db: db_path(db) for db in DATABASES}
    trimmed = tmp_path_factory.mktemp("spider") / "flight_2.sqlite"
    shutil.copyfile(paths["flight_2"], trimmed)
    with sqlite3.connect(trimmed) as conn:
        for statement in TRIM:
            conn.execute(statement)
    paths["flight_2"] = trimmed
    return paths


@pytest.mark.parametrize("item_id", sorted(INTENTS))
def test_the_hand_written_intent_returns_the_gold_rows(
    item_id: str, databases: dict[str, Path]
) -> None:
    db, item = _items()[item_id]
    assert item.gold_sql is not None
    literals = [a or b for a, b in _QUOTED.findall(item.gold_sql)]
    entity, body = INTENTS[item_id]
    intent = Intent.model_validate(_fill({"entity": entity, **body}, literals))
    result = validate(intent, _registry(db), now=NOW, allow_draft=True)
    assert result.plan is not None, result.issues
    engine = readonly_engine(f"sqlite:///{databases[db]}")
    try:
        got = run(engine, build(result.plan), row_cap=ROW_CAP).rows
        gold = run(engine, raw_sql(item.gold_sql), row_cap=ROW_CAP).rows
    finally:
        engine.dispose()
    matches = results_match(got, gold, ordered=item.ordered, row_cap=ROW_CAP)
    # No student has two likes, so these two golds are empty; every other gold has rows.
    assert bool(gold) != (item_id in {"spider:908", "spider:909"})
    assert matches != (item_id in GOLD_DIFFERS), (got[:5], gold[:5])


def test_how_many_match_the_gold() -> None:
    # The plan's target was 55 of 62; see the Phase 2 notes in builds/v03/log.md.
    assert set(GOLD_DIFFERS) <= set(INTENTS)
    assert len(INTENTS) - len(GOLD_DIFFERS) == 42
