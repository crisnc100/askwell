"""Inferred links (v0.3, PR-2, switch `inferred_links`): a column named after a table
(`airline`, `origin_airport_id`) links to it only when its values are that table's keys,
with enough of them to be evidence; a declared key to a unique column is kept."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import Engine, column, func, select, table

from askwell.bench.spider import db_path
from askwell.core.executor import readonly_engine
from askwell.core.features import ALL
from askwell.core.registry import Registry, Relationship
from askwell.core.registry_init import MIN_DISTINCT_FOR_LINK, init_registry
from tests.core.dual import pg_db, sqlite_db

NO_INFERENCE = ALL - {"inferred_links"}
SEEN_SPIDER = ["car_1", "dog_kennels", "flight_2", "network_1", "wta_1"]


def _rows(name: str, values: list[str]) -> str:
    return f"INSERT INTO {name} VALUES " + ", ".join(values)


KEYS = range(1, 13)

STATEMENTS = [
    "CREATE TABLE airlines (uid INTEGER PRIMARY KEY, name TEXT)",
    _rows("airlines", [f"({k}, 'line {k}')" for k in KEYS]),
    "CREATE TABLE airports (id INTEGER PRIMARY KEY, city TEXT)",
    _rows("airports", [f"({k}, 'city {k}')" for k in KEYS]),
    # airline: the singular of a table's name, all 12 keys.
    # origin_airport_id: a role, then a table's singular, then _id.
    # few_airport_id: 9 distinct values, under the evidence floor.
    # stray_airport_id: one value that is no airport's key.
    "CREATE TABLE flights (id INTEGER PRIMARY KEY, airline INTEGER, "
    "origin_airport_id INTEGER, few_airport_id INTEGER, stray_airport_id INTEGER, "
    "flight TEXT)",
    _rows(
        "flights",
        [f"({k}, {k}, {13 - k}, {min(k, 9)}, {99 if k == 1 else k}, 'f{k}')" for k in KEYS],
    ),
    "CREATE TABLE game (id INTEGER PRIMARY KEY)",
    "CREATE TABLE games (id INTEGER PRIMARY KEY)",
    _rows("game", [f"({k})" for k in KEYS]),
    _rows("games", [f"({k})" for k in KEYS]),
    "CREATE TABLE scores (id INTEGER PRIMARY KEY, game INTEGER)",
    _rows("scores", [f"({k}, {k})" for k in KEYS]),
    "CREATE TABLE model_list (id INTEGER PRIMARY KEY, model TEXT UNIQUE)",
    _rows("model_list", [f"({k}, 'm{k}')" for k in KEYS]),
    "CREATE TABLE car_names (id INTEGER PRIMARY KEY, model TEXT REFERENCES model_list(model))",
    _rows("car_names", [f"({k}, 'm{k}')" for k in KEYS]),
]


def _links(registry: Registry) -> set[tuple[str, str, str, str]]:
    return {(r.from_entity, r.from_field, r.to_entity, r.to_field) for r in registry.relationships}


@pytest.fixture
def engines(pg_owner: Engine, tmp_path: Path) -> Iterator[list[Engine]]:
    with (
        pg_db(pg_owner, "askwell_test_inferred", STATEMENTS) as pg,
        sqlite_db(tmp_path / "inferred.sqlite", STATEMENTS) as lite,
    ):
        yield [pg, lite]


def test_a_column_named_after_a_table_links_when_its_values_are_keys(
    engines: list[Engine],
) -> None:
    for engine in engines:
        links = _links(init_registry(engine).registry)
        assert ("flights", "airline", "airlines", "uid") in links
        assert ("flights", "origin_airport_id", "airports", "id") in links


def test_too_few_values_or_a_stray_value_is_not_evidence(engines: list[Engine]) -> None:
    for engine in engines:
        result = init_registry(engine)
        froms = {(r.from_entity, r.from_field) for r in result.registry.relationships}
        assert ("flights", "few_airport_id") not in froms
        assert ("flights", "stray_airport_id") not in froms
        assert any("flights.stray_airport_id" in w for w in result.warnings)
        # Words never name a link, however they read.
        assert ("flights", "flight") not in froms


def test_two_tables_the_name_fits_equally_give_no_link(engines: list[Engine]) -> None:
    for engine in engines:
        result = init_registry(engine)
        assert ("scores", "game") not in {
            (r.from_entity, r.from_field) for r in result.registry.relationships
        }
        assert any("scores.game" in w and "several" in w for w in result.warnings)


def test_a_declared_key_to_a_unique_column_is_kept(engines: list[Engine]) -> None:
    for engine in engines:
        rels = init_registry(engine).registry.relationships
        kept = [r for r in rels if r.from_entity == "car_names"]
        assert kept == [
            Relationship(
                from_entity="car_names",
                from_field="model",
                to_entity="model_list",
                to_field="model",
                source="declared",
            )
        ]


def test_a_table_never_links_to_itself_by_name(tmp_path: Path) -> None:
    statements = [
        "CREATE TABLE worker (id INTEGER PRIMARY KEY, manager_worker_id INTEGER)",
        _rows("worker", [f"({k}, {k})" for k in KEYS]),
    ]
    with sqlite_db(tmp_path / "self.sqlite", statements) as engine:
        assert init_registry(engine).registry.relationships == []


# --- the switch off restores today's links (P2.5) ---


def test_switch_off_infers_only_todays_links(engines: list[Engine]) -> None:
    for engine in engines:
        result = init_registry(engine, features=NO_INFERENCE)
        assert _links(result.registry) == set()
        assert any("car_names.model" in w and "not a primary key" in w for w in result.warnings)


# --- P2.2: every new link on the seen Spider databases holds its evidence ---


@pytest.mark.parametrize("db_id", SEEN_SPIDER)
def test_new_links_on_seen_spider_hold_their_evidence(db_id: str) -> None:
    path = db_path(db_id)
    if not path.exists():
        pytest.fail(f"{path}: run `uv run python -m scripts.fetch_benchmarks`")
    engine = readonly_engine(f"sqlite:///{path}")
    try:
        on = init_registry(engine).registry
        today = _links(init_registry(engine, features=NO_INFERENCE).registry)
        for rel in on.relationships:
            if rel.source != "inferred" or (
                (rel.from_entity, rel.from_field, rel.to_entity, rel.to_field) in today
            ):
                continue
            src = on.entities[rel.from_entity]
            dst = on.entities[rel.to_entity]
            src_table = table(src.table, column(src.fields[rel.from_field].column))
            dst_table = table(dst.table, column(dst.fields[rel.to_field].column))
            value = src_table.c[src.fields[rel.from_field].column]
            key = dst_table.c[dst.fields[rel.to_field].column]
            with engine.connect() as conn:
                distinct = conn.execute(select(func.count(value.distinct()))).scalar_one()
                missing = conn.execute(
                    select(func.count()).where(value.is_not(None), value.not_in(select(key)))
                ).scalar_one()
            assert distinct >= MIN_DISTINCT_FOR_LINK, rel
            assert missing == 0, rel
    finally:
        engine.dispose()
