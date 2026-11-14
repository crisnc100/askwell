"""Stable answers (v0.3, PR-1): grouping by an entity's label groups by its key too,
rows that tie come back in one order on every engine, and a top-N says when the next row
ties with its last."""

from __future__ import annotations

import sqlite3
from decimal import Decimal
from itertools import pairwise
from pathlib import Path
from typing import Any

import pytest
import yaml
from pydantic import ValidationError
from sqlalchemy import Engine

from askwell.core.executor import Executor, readonly_engine, run
from askwell.core.registry import EntityDef, FieldDef, Registry, Relationship, dump_registry
from askwell.core.registry_init import infer_label, init_registry
from askwell.core.sqlbuild import build, peeks, values_tie
from askwell.core.validate import QueryPlan
from tests.core.conftest import check
from tests.core.rows import normalise

GARCIA = {"field": "customers.name", "op": "eq", "value": "Garcia Ltd"}


def _plan(registry: Registry, **intent: Any) -> QueryPlan:
    result = check(registry, **intent)
    assert result.plan is not None, result.issues
    return result.plan


def _both(pg: Engine, lite: Engine, plan: QueryPlan) -> tuple[Any, Any]:
    return run(pg, build(plan)), run(lite, build(plan))


# --- grouping by a label ---


def test_two_customers_with_one_name_stay_two_rows(
    registry: Registry, pg_seeded: Engine, sqlite_ro: Engine
) -> None:
    plan = _plan(
        registry,
        intent_type="grouped_summary",
        entity="sites",
        metrics=[{"agg": "count", "alias": "n"}],
        group_by=[{"field": "customers.name"}],
        filters=[GARCIA],
    )
    for result in _both(pg_seeded, sqlite_ro, plan):
        assert result.columns == ["customers__id", "customers__name", "n"]
        assert normalise(result.rows, ordered=True) == [
            (56.0, "Garcia Ltd", 1.0),
            (144.0, "Garcia Ltd", 1.0),
        ]


def test_grouping_by_a_plain_attribute_groups_by_its_value(
    registry: Registry, pg_seeded: Engine, sqlite_ro: Engine
) -> None:
    plan = _plan(
        registry,
        intent_type="grouped_summary",
        entity="sites",
        metrics=[{"agg": "count", "alias": "n"}],
        group_by=[{"field": "customers.region"}],
    )
    assert plan.group_by[0].key is None
    for result in _both(pg_seeded, sqlite_ro, plan):
        assert result.columns == ["customers__region", "n"]
        assert len(result.rows) == 5


def test_a_label_on_the_base_entity_returns_its_key(registry: Registry) -> None:
    plan = _plan(
        registry,
        intent_type="grouped_summary",
        entity="technicians",
        metrics=[{"agg": "avg", "field": "hourly_rate", "alias": "rate"}],
        group_by=[{"field": "full_name"}],
    )
    key = plan.group_by[0].key
    assert key is not None
    assert (key.entity, key.name, key.label) == ("technicians", "id", "id")


def test_grouping_by_the_key_and_the_label_adds_no_second_key(registry: Registry) -> None:
    plan = _plan(
        registry,
        intent_type="grouped_summary",
        entity="sites",
        metrics=[{"agg": "count", "alias": "n"}],
        group_by=[{"field": "customers.name"}, {"field": "customers.id"}],
    )
    assert [g.key for g in plan.group_by] == [None, None]


def test_a_metric_cannot_take_the_key_columns_label(registry: Registry) -> None:
    result = check(
        registry,
        intent_type="grouped_summary",
        entity="sites",
        metrics=[{"agg": "count", "alias": "customers__id"}],
        group_by=[{"field": "customers.name"}],
    )
    assert result.codes == ["alias_collision"]


# --- one order inside ties ---


def test_tied_groups_come_back_in_one_order_on_both_engines(
    registry: Registry, pg_seeded: Engine, sqlite_ro: Engine
) -> None:
    plan = _plan(
        registry,
        intent_type="grouped_summary",
        entity="work_orders",
        metrics=[{"agg": "count", "alias": "jobs"}],
        group_by=[{"field": "sites.city"}],
        date_range={"field": "opened_at", "relative": "last_quarter"},
        order_by=[{"target": "jobs", "direction": "desc"}],
    )
    pg, lite = _both(pg_seeded, sqlite_ro, plan)
    rows = normalise(pg.rows, ordered=True)
    assert rows == normalise(lite.rows, ordered=True)
    counts = [row[1] for row in rows]
    assert len(set(counts)) < len(counts), "the case needs ties to mean anything"
    for above, below in pairwise(rows):
        if above[1] == below[1]:
            assert str(above[0]) < str(below[0])


def test_tied_rows_in_a_list_come_back_in_key_order_on_both_engines(
    registry: Registry, pg_seeded: Engine, sqlite_ro: Engine
) -> None:
    plan = _plan(
        registry,
        intent_type="row_list",
        entity="work_orders",
        select=["id", "priority"],
        order_by=[{"target": "priority"}],
        limit=50,
    )
    assert [f.name for f in plan.tiebreak] == ["id"]
    pg, lite = _both(pg_seeded, sqlite_ro, plan)
    rows = normalise(pg.rows, ordered=True)
    assert rows == normalise(lite.rows, ordered=True)
    assert rows == sorted(rows, key=lambda r: (str(r[1]), r[0]))


# --- a top-N that cuts a tie ---


def _busiest(limit: int) -> dict[str, Any]:
    return {
        "intent_type": "grouped_summary",
        "entity": "work_orders",
        "metrics": [{"agg": "count", "alias": "jobs"}],
        "group_by": [{"field": "technicians.full_name"}],
        "filters": [{"field": "status", "op": "eq", "value": "completed"}],
        "date_range": {"field": "completed_at", "relative": "last_n_days", "n": 90},
        "order_by": [{"target": "jobs", "direction": "desc"}],
        "limit": limit,
    }


@pytest.mark.parametrize("engine_name", ["postgresql", "sqlite"])
@pytest.mark.parametrize(("limit", "tied"), [(5, True), (3, False)])
def test_a_top_n_says_when_the_next_row_ties_with_its_last(
    registry: Registry,
    pg_seeded: Engine,
    sqlite_ro: Engine,
    engine_name: str,
    limit: int,
    tied: bool,
) -> None:
    # In the last 90 days three technicians tie at 21 jobs for places 4 and 5; places
    # 1 to 3 hold 24, 23 and 23, and the 4th row has 21.
    engine = pg_seeded if engine_name == "postgresql" else sqlite_ro
    execution = Executor(engine).execute(_plan(registry, **_busiest(limit)))
    assert execution.tied_at_cutoff is tied
    assert len(execution.result.rows) == limit
    assert execution.result.columns == ["technicians__id", "technicians__full_name", "jobs"]
    assert limit + 1 in execution.params.values()  # the extra row was fetched, then dropped


@pytest.mark.parametrize("engine_name", ["postgresql", "sqlite"])
def test_a_list_ordered_by_an_unselected_field_drops_the_extra_column(
    registry: Registry, pg_seeded: Engine, sqlite_ro: Engine, engine_name: str
) -> None:
    engine = pg_seeded if engine_name == "postgresql" else sqlite_ro
    plan = _plan(
        registry,
        intent_type="row_list",
        entity="work_orders",
        select=["id"],
        order_by=[{"target": "priority"}],
        limit=3,
    )
    execution = Executor(engine).execute(plan)
    assert execution.result.columns == ["id"]
    assert len(execution.result.rows) == 3
    # Hundreds of work orders share each priority, so the 4th ties with the 3rd.
    assert execution.tied_at_cutoff is True


def test_no_peek_without_a_limit_an_order_or_room_under_the_row_cap(registry: Registry) -> None:
    ordered = _plan(registry, **_busiest(5))
    assert peeks(ordered, row_cap=1000)
    assert not peeks(ordered, row_cap=5)
    unordered = _plan(registry, **{**_busiest(5), "order_by": []})
    assert not peeks(unordered, row_cap=1000)
    unlimited = _plan(registry, **{**_busiest(5), "limit": None})
    assert not peeks(unlimited, row_cap=1000)


def test_an_unpeeked_query_keeps_its_own_limit(registry: Registry, sqlite_ro: Engine) -> None:
    execution = Executor(sqlite_ro, row_cap=5).execute(_plan(registry, **_busiest(5)))
    assert len(execution.result.rows) == 5
    assert execution.tied_at_cutoff is False


def test_values_tie_within_the_scorer_tolerance() -> None:
    assert values_tie(0.1 + 0.2, Decimal("0.3"))
    assert values_tie(21, 21.0)
    assert not values_tie(21, 21.01)
    assert values_tie(None, None)
    assert not values_tie(None, 0)
    assert values_tie("Boston", "Boston")


def test_a_float_sum_tie_is_found_on_sqlite(tmp_path: Path) -> None:
    path = tmp_path / "sums.sqlite"
    con = sqlite3.connect(path)
    con.executescript(
        """
        CREATE TABLE lines (id INTEGER PRIMARY KEY, team TEXT, amount REAL);
        INSERT INTO lines (team, amount) VALUES
          ('a', 0.1), ('a', 0.2), ('b', 0.3), ('c', 5.0);
        """
    )
    con.commit()
    con.close()
    registry = Registry(
        schema_version=1,
        draft=False,
        entities={
            "lines": EntityDef(
                table="lines",
                primary_key=["id"],
                fields={
                    "id": FieldDef(column="id", type="integer"),
                    "team": FieldDef(column="team", type="text"),
                    "amount": FieldDef(column="amount", type="number", aggregatable=True),
                },
            )
        },
    )
    plan = _plan(
        registry,
        intent_type="grouped_summary",
        entity="lines",
        metrics=[{"agg": "sum", "field": "amount", "alias": "total"}],
        group_by=[{"field": "team"}],
        order_by=[{"target": "total", "direction": "desc"}],
        limit=2,
    )
    engine = readonly_engine(f"sqlite:///{path}")
    try:
        execution = Executor(engine).execute(plan)
    finally:
        engine.dispose()
    assert execution.tied_at_cutoff is True
    assert [row[0] for row in execution.result.rows] == ["c", "a"]


# --- the registry's label ---


def _entity(**changes: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "table": "things",
        "primary_key": ["id"],
        "label": "name",
        "fields": {
            "id": {"column": "id", "type": "integer"},
            "name": {"column": "name", "type": "text"},
            "secret": {"column": "secret", "type": "text", "hidden": True},
        },
    }
    return {**base, **changes}


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"label": "nope"}, "is not a field"),
        ({"primary_key": ["id", "name"]}, "single-field primary key"),
        ({"primary_key": []}, "single-field primary key"),
        ({"label": "id"}, "cannot be the primary key"),
        ({"label": "secret"}, "is hidden"),
    ],
)
def test_a_label_must_name_a_visible_field_beside_a_single_key(
    changes: dict[str, Any], message: str
) -> None:
    with pytest.raises(ValidationError, match=message):
        EntityDef.model_validate(_entity(**changes))


def test_the_label_is_written_only_when_set() -> None:
    def dumped(label: str | None) -> dict[str, Any]:
        registry = Registry(
            schema_version=1,
            draft=False,
            entities={"things": EntityDef.model_validate(_entity(label=label))},
        )
        return yaml.safe_load(dump_registry(registry))["entities"]["things"]

    assert "label" not in dumped(None)
    assert dumped("name")["label"] == "name"


# --- the label registry init infers ---


def _text(column: str, hidden: bool = False) -> FieldDef:
    return FieldDef(column=column, type="text", hidden=hidden)


ID = FieldDef(column="id", type="integer")


@pytest.mark.parametrize(
    ("entity", "fields", "key", "label"),
    [
        ("customers", {"id": ID, "name": _text("Name")}, ["id"], "name"),
        ("staff", {"id": ID, "full_name": _text("full_name")}, ["id"], "full_name"),
        ("films", {"id": ID, "title": _text("title")}, ["id"], "title"),
        ("airports", {"id": ID, "airport_name": _text("airport_name")}, ["id"], "airport_name"),
        ("airports", {"id": ID, "airports_name": _text("airports_name")}, ["id"], "airports_name"),
        # two candidates, a hidden one, a number, a composite key, no key: no label
        ("people", {"id": ID, "name": _text("name"), "title": _text("title")}, ["id"], None),
        ("people", {"id": ID, "name": _text("name", hidden=True)}, ["id"], None),
        ("people", {"id": ID, "name": FieldDef(column="name", type="integer")}, ["id"], None),
        ("people", {"id": ID, "name": _text("name"), "b": ID}, ["id", "b"], None),
        ("people", {"id": ID, "name": _text("name")}, [], None),
        ("people", {"id": ID, "first_name": _text("first_name")}, ["id"], None),
    ],
)
def test_registry_init_infers_a_label_only_from_one_clear_name(
    entity: str, fields: dict[str, FieldDef], key: list[str], label: str | None
) -> None:
    assert infer_label(entity, key, fields) == label


def test_registry_init_writes_the_label(tmp_path: Path) -> None:
    path = tmp_path / "shop.sqlite"
    con = sqlite3.connect(path)
    con.executescript(
        "CREATE TABLE customers (id INTEGER PRIMARY KEY, name TEXT, city TEXT);"
        "CREATE TABLE notes (body TEXT, name TEXT);"
    )
    con.close()
    engine = readonly_engine(f"sqlite:///{path}")
    try:
        registry = init_registry(engine).registry
    finally:
        engine.dispose()
    assert registry.entities["customers"].label == "name"
    assert registry.entities["notes"].label is None


# --- review fixes: a hidden key, a composite key ---


def _people_db(tmp_path: Path) -> Path:
    path = tmp_path / "people.sqlite"
    con = sqlite3.connect(path)
    con.executescript(
        """
        CREATE TABLE customers (id INTEGER PRIMARY KEY, name TEXT);
        CREATE TABLE orders (id INTEGER PRIMARY KEY, customer_id INTEGER, total REAL);
        INSERT INTO customers VALUES (1, 'Garcia Ltd'), (2, 'Garcia Ltd'), (3, 'Akron Co');
        INSERT INTO orders (customer_id, total) VALUES (1, 10), (2, 20), (2, 5), (3, 1);
        CREATE TABLE lines (order_id INTEGER, line_no INTEGER, sku TEXT,
                            PRIMARY KEY (order_id, line_no));
        INSERT INTO lines VALUES (2, 1, 'x'), (1, 2, 'x'), (1, 1, 'x'), (2, 2, 'y');
        """
    )
    con.commit()
    con.close()
    return path


def _people_registry(hide_key: bool) -> Registry:
    return Registry(
        schema_version=1,
        draft=False,
        entities={
            "customers": EntityDef(
                table="customers",
                primary_key=["id"],
                label="name",
                fields={
                    "id": FieldDef(column="id", type="integer", hidden=hide_key),
                    "name": FieldDef(column="name", type="text"),
                },
            ),
            "orders": EntityDef(
                table="orders",
                primary_key=["id"],
                fields={
                    "id": FieldDef(column="id", type="integer"),
                    "customer_id": FieldDef(column="customer_id", type="integer"),
                    "total": FieldDef(column="total", type="number", aggregatable=True),
                },
            ),
            "lines": EntityDef(
                table="lines",
                primary_key=["order_id", "line_no"],
                fields={
                    "order_id": FieldDef(column="order_id", type="integer"),
                    "line_no": FieldDef(column="line_no", type="integer"),
                    "sku": FieldDef(column="sku", type="text"),
                },
            ),
        },
        relationships=[
            Relationship(
                from_entity="orders",
                from_field="customer_id",
                to_entity="customers",
                to_field="id",
                source="declared",
            )
        ],
    )


def _run_sqlite(path: Path, plan: QueryPlan) -> Any:
    engine = readonly_engine(f"sqlite:///{path}")
    try:
        return run(engine, build(plan))
    finally:
        engine.dispose()


def test_a_hidden_key_still_keeps_same_named_customers_apart(tmp_path: Path) -> None:
    path = _people_db(tmp_path)
    plan = _plan(
        _people_registry(hide_key=True),
        intent_type="grouped_summary",
        entity="orders",
        metrics=[{"agg": "sum", "field": "total", "alias": "spent"}],
        group_by=[{"field": "customers.name"}],
        order_by=[{"target": "spent", "direction": "desc"}],
    )
    result = _run_sqlite(path, plan)
    # The hidden id groups the rows but is never shown.
    assert result.columns == ["customers__name", "spent"]
    assert normalise(result.rows, ordered=True) == [
        ("Garcia Ltd", 25.0),
        ("Garcia Ltd", 10.0),
        ("Akron Co", 1.0),
    ]


def test_a_shown_key_is_returned(tmp_path: Path) -> None:
    plan = _plan(
        _people_registry(hide_key=False),
        intent_type="grouped_summary",
        entity="orders",
        metrics=[{"agg": "sum", "field": "total", "alias": "spent"}],
        group_by=[{"field": "customers.name"}],
    )
    assert _run_sqlite(_people_db(tmp_path), plan).columns == [
        "customers__id",
        "customers__name",
        "spent",
    ]


def test_a_composite_key_orders_a_list_by_every_key_field(tmp_path: Path) -> None:
    plan = _plan(
        _people_registry(hide_key=False),
        intent_type="row_list",
        entity="lines",
        select=["sku", "order_id", "line_no"],
        order_by=[{"target": "sku"}],
    )
    assert [f.name for f in plan.tiebreak] == ["order_id", "line_no"]
    rows = _run_sqlite(_people_db(tmp_path), plan).rows
    assert [tuple(r) for r in rows] == [("x", 1, 1), ("x", 1, 2), ("x", 2, 1), ("y", 2, 2)]
