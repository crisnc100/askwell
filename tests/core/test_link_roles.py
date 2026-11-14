"""Named links (v0.3, PR-2, switch `link_roles`): when two tables are linked twice, a
field across them names the link, `entity@link.field`, and each named link is its own
join, on both engines. With the switch off the refusal is today's."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import Engine

from askwell.core.executor import run
from askwell.core.features import ALL
from askwell.core.intent import Intent
from askwell.core.registry import EntityDef, FieldDef, Registry, Relationship
from askwell.core.sqlbuild import build
from askwell.core.validate import QueryPlan, ValidationResult, validate
from askwell.pipeline.prompt import registry_view
from tests.core.conftest import NOW
from tests.core.dual import pg_db, sqlite_db
from tests.core.rows import normalise

NO_ROLES = ALL - {"link_roles"}

STATEMENTS = [
    "CREATE TABLE airports (id INTEGER PRIMARY KEY, city TEXT)",
    "CREATE TABLE flights (id INTEGER PRIMARY KEY, origin_id INTEGER, dest_id INTEGER)",
    "INSERT INTO airports VALUES (1, 'Avon'), (2, 'Brent'), (3, 'Cork')",
    "INSERT INTO flights VALUES (1, 1, 2), (2, 1, 3), (3, 2, 3), (4, 3, 1)",
]

REGISTRY = Registry(
    schema_version=1,
    draft=False,
    entities={
        "airports": EntityDef(
            table="airports",
            primary_key=["id"],
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
            from_field="origin_id",
            to_entity="airports",
            to_field="id",
            source="declared",
        ),
        Relationship(
            from_entity="flights",
            from_field="dest_id",
            to_entity="airports",
            to_field="id",
            source="declared",
        ),
    ],
)


def _check(features: frozenset[str] = ALL, **intent: Any) -> ValidationResult:
    return validate(Intent.model_validate(intent), REGISTRY, now=NOW, features=features)


def _plan(**intent: Any) -> QueryPlan:
    result = _check(**intent)
    assert result.plan is not None, result.issues
    return result.plan


@pytest.fixture
def engines(pg_owner: Engine, tmp_path: Path) -> Iterator[list[Engine]]:
    with (
        pg_db(pg_owner, "askwell_test_links", STATEMENTS) as pg,
        sqlite_db(tmp_path / "links.sqlite", STATEMENTS) as lite,
    ):
        yield [pg, lite]


def test_each_named_link_is_its_own_join(engines: list[Engine]) -> None:
    plan = _plan(
        intent_type="row_list",
        entity="flights",
        select=["id", "airports@origin_id.city", "airports@dest_id.city"],
        order_by=[{"target": "id"}],
    )
    assert len(plan.joins) == 2
    for engine in engines:
        result = run(engine, build(plan))
        assert result.columns == ["id", "airports_origin_id__city", "airports_dest_id__city"]
        assert normalise(result.rows, ordered=True) == [
            (1.0, "Avon", "Brent"),
            (2.0, "Avon", "Cork"),
            (3.0, "Brent", "Cork"),
            (4.0, "Cork", "Avon"),
        ]


def test_group_by_one_link_and_filter_on_the_other(engines: list[Engine]) -> None:
    plan = _plan(
        intent_type="grouped_summary",
        entity="flights",
        metrics=[{"agg": "count", "alias": "n"}],
        group_by=[{"field": "airports@dest_id.city"}],
        filters=[{"field": "airports@origin_id.city", "op": "eq", "value": "Avon"}],
        order_by=[{"target": "airports@dest_id.city"}],
    )
    for engine in engines:
        result = run(engine, build(plan))
        assert normalise(result.rows, ordered=True) == [("Brent", 1.0), ("Cork", 1.0)]


def test_the_same_link_twice_is_one_join() -> None:
    plan = _plan(
        intent_type="row_list",
        entity="flights",
        select=["airports@origin_id.city"],
        filters=[{"field": "airports@origin_id.city", "op": "eq", "value": "Avon"}],
    )
    assert len(plan.joins) == 1


def test_link_names_match_without_case() -> None:
    assert _check(intent_type="row_list", entity="flights", select=["airports@Origin_ID.city"]).ok


def test_an_unnamed_field_across_two_links_names_them_in_the_refusal() -> None:
    result = _check(intent_type="row_list", entity="flights", select=["airports.city"])
    assert result.codes == ["ambiguous_path"]
    assert "airports@dest_id.city, airports@origin_id.city" in result.issues[0].message


def test_a_link_that_does_not_lead_to_the_entity_is_refused() -> None:
    result = _check(intent_type="row_list", entity="flights", select=["airports@nope.city"])
    assert result.codes == ["unknown_link"]
    assert "dest_id, origin_id" in result.issues[0].message


def test_a_named_link_into_the_base_entity_is_refused() -> None:
    result = _check(intent_type="row_list", entity="airports", select=["airports@origin_id.city"])
    assert result.codes == ["unknown_link"]


# --- the switch off restores today's refusal (P2.5) ---


def test_switch_off_refuses_a_named_link_as_an_unknown_entity() -> None:
    result = _check(
        NO_ROLES, intent_type="row_list", entity="flights", select=["airports@dest_id.city"]
    )
    assert result.codes == ["unknown_entity"]


def test_switch_off_keeps_the_ambiguous_path_message_unchanged() -> None:
    result = _check(NO_ROLES, intent_type="row_list", entity="flights", select=["airports.city"])
    assert result.codes == ["ambiguous_path"]
    assert result.issues[0].message == "2 equally short paths from flights to airports"


# --- the prompt describes named links only where a schema has them ---


def test_prompt_names_each_link_when_two_tables_are_linked_twice() -> None:
    text = registry_view(REGISTRY, NOW, 16000).text
    assert "Named links:" in text
    assert "- airports@origin_id.<field>: through flights.origin_id" in text
    assert "- airports@dest_id.<field>: through flights.dest_id" in text


def test_prompt_has_no_named_links_with_the_switch_off() -> None:
    assert "Named links" not in registry_view(REGISTRY, NOW, 16000, features=NO_ROLES).text


def test_prompt_for_a_schema_without_double_links_is_unchanged(registry: Registry) -> None:
    on = registry_view(registry, NOW, 16000).text
    assert on == registry_view(registry, NOW, 16000, features=frozenset()).text
    assert "Named links" not in on
