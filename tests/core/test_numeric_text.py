"""Numbers stored as text (v0.3, PR-2, switch `numeric_text`): a text column whose
values all read as numbers is drafted as a number, its placeholders ('null', 'N/A', '')
read as NULL on both engines, and columns that only look numeric stay text."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import Engine

from askwell.core.executor import readonly_engine, run
from askwell.core.features import ALL
from askwell.core.intent import Intent
from askwell.core.registry import FieldDef, Registry
from askwell.core.registry_init import init_registry
from askwell.core.sqlbuild import build
from askwell.core.validate import ValidationResult, validate
from tests.core.conftest import NOW
from tests.core.dual import pg_db, sqlite_db
from tests.core.rows import normalise

NO_NUMBERS = ALL - {"numeric_text"}

STATEMENTS = [
    "CREATE TABLE cars (id INTEGER PRIMARY KEY, mpg TEXT, horsepower TEXT, zip TEXT, "
    "part_code TEXT, owner_id TEXT, model TEXT, empty TEXT)",
    "INSERT INTO cars VALUES "
    "(1, '18', '130', '01234', '12', '7', 'alpha', 'null'), "
    "(2, '15.5', 'N/A', '90210', '13', '8', 'beta', NULL), "
    "(3, ' 20 ', '165', '10001', '14', '9', 'gamma', ''), "
    "(4, 'null', '-', '20002', '15', '10', 'delta', 'n/a'), "
    "(5, '', 'NULL', '30003', '16', '11', 'eps', '-'), "
    "(6, '25', '90', '40004', '17', '12', 'zeta', ''), "
    "(7, '30', '110', '50005', '18', '13', 'eta', ''), "
    "(8, '12', '150', '60006', '19', '14', 'theta', ''), "
    "(9, '22', '200', '70007', '20', '15', 'iota', '')",
]


def _fields(registry: Registry) -> dict[str, FieldDef]:
    return registry.entities["cars"].fields


@pytest.fixture
def engines(pg_owner: Engine, tmp_path: Path) -> Iterator[list[Engine]]:
    with (
        pg_db(pg_owner, "askwell_test_numtext", STATEMENTS) as pg,
        sqlite_db(tmp_path / "numtext.sqlite", STATEMENTS) as lite,
    ):
        yield [pg, lite]


def _check(registry: Registry, features: frozenset[str] = ALL, **intent: Any) -> ValidationResult:
    return validate(
        Intent.model_validate(intent), registry, now=NOW, allow_draft=True, features=features
    )


def test_drafting_finds_the_number_columns(engines: list[Engine]) -> None:
    for engine in engines:
        fields = _fields(init_registry(engine, include_values=True).registry)
        for name in ("mpg", "horsepower"):
            assert fields[name].type == "number", name
            assert fields[name].text_number, name
            assert fields[name].aggregatable, name
        # A leading zero, a code or id name, words, and placeholders alone all stay text.
        for name in ("zip", "part_code", "owner_id", "model", "empty"):
            assert fields[name].type == "text", name
            assert not fields[name].text_number, name


def test_placeholders_read_as_null_on_both_engines(engines: list[Engine]) -> None:
    for engine in engines:
        registry = init_registry(engine).registry
        result = _check(
            registry,
            intent_type="summary",
            entity="cars",
            metrics=[
                {"agg": "avg", "field": "mpg", "alias": "avg_mpg"},
                {"agg": "sum", "field": "horsepower", "alias": "hp"},
                {"agg": "count", "field": "mpg", "alias": "n_mpg"},
            ],
        )
        assert result.plan is not None, result.issues
        [(avg, hp, n)] = normalise(run(engine, build(result.plan)).rows, ordered=True)
        assert avg == pytest.approx((18 + 15.5 + 20 + 25 + 30 + 12 + 22) / 7)
        assert (hp, n) == (845.0, 7.0)


def test_a_text_number_filters_as_a_number(engines: list[Engine]) -> None:
    for engine in engines:
        registry = init_registry(engine).registry
        result = _check(
            registry,
            intent_type="row_list",
            entity="cars",
            select=["id"],
            filters=[{"field": "mpg", "op": "gt", "value": 16}],
            order_by=[{"target": "id"}],
        )
        assert result.plan is not None, result.issues
        assert normalise(run(engine, build(result.plan)).rows, ordered=True) == [
            (1.0,),
            (3.0,),
            (6.0,),
            (7.0,),
            (9.0,),
        ]


def test_placeholders_are_bound_values_not_sql_text(engines: list[Engine]) -> None:
    registry = init_registry(engines[1]).registry
    result = _check(registry, intent_type="row_list", entity="cars", select=["id", "mpg"])
    assert result.plan is not None
    compiled = build(result.plan).compile()
    assert "N/A" not in str(compiled)
    assert "N/A" in compiled.params.values()


# --- the switch off restores today's behaviour (P2.5) ---


def test_switch_off_drafts_text(engines: list[Engine]) -> None:
    for engine in engines:
        fields = _fields(init_registry(engine, features=NO_NUMBERS).registry)
        assert fields["mpg"].type == "text"
        assert not fields["mpg"].text_number


def test_switch_off_refuses_a_sum_over_a_drafted_text_number(engines: list[Engine]) -> None:
    registry = init_registry(engines[1]).registry
    intent: dict[str, Any] = {
        "intent_type": "summary",
        "entity": "cars",
        "metrics": [{"agg": "sum", "field": "mpg"}],
    }
    assert _check(registry, **intent).ok
    off = _check(registry, NO_NUMBERS, **intent)
    assert not off.ok
    today = init_registry(engines[1], features=NO_NUMBERS).registry
    assert off.codes == _check(today, NO_NUMBERS, **intent).codes


CODES = [
    "CREATE TABLE pets (id INTEGER PRIMARY KEY, flag_yn TEXT, sex TEXT, years TEXT)",
    "INSERT INTO pets VALUES "
    "(1, '0', '1', '2'), (2, '1', '0', '3'), (3, '1', '1', '4'), (4, 'null', '0', '5'), "
    "(5, '0', '1', '6'), (6, '1', '1', '7')",
]


def test_a_column_of_a_few_number_codes_stays_categorical_text(tmp_path: Path) -> None:
    # 0/1 flags and small code sets keep their value list for the model; a column with
    # more distinct numbers than CODE_MAX is a quantity.
    with sqlite_db(tmp_path / "codes.sqlite", CODES) as engine:
        fields = _fields_of(init_registry(engine, include_values=True).registry, "pets")
    for name in ("flag_yn", "sex"):
        assert fields[name].type == "text", name
        assert not fields[name].text_number, name
        assert fields[name].categorical, name
    assert fields["flag_yn"].allowed_values == ["0", "1", "null"]
    assert fields["years"].type == "number"
    assert fields["years"].text_number


def test_dog_kennels_flags_keep_their_values() -> None:
    from askwell.bench.spider import db_path

    engine = readonly_engine(f"sqlite:///{db_path('dog_kennels')}")
    try:
        fields = _fields_of(init_registry(engine, include_values=True).registry, "dogs")
    finally:
        engine.dispose()
    for name in ("gender", "abandoned_yn"):
        assert fields[name].type == "text", name
        assert fields[name].allowed_values == ["0", "1"], name
    for name in ("age", "weight"):
        assert fields[name].text_number, name


def _fields_of(registry: Registry, entity: str) -> dict[str, FieldDef]:
    return registry.entities[entity].fields
