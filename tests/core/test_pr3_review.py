"""PR-3 review fixes: a named link in `has` obeys the link_roles switch; arithmetic on
integer fields keeps its fractions on both engines; a computed value's name never
shadows a field."""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import Engine, text

from askwell.core.executor import run
from askwell.core.features import ALL
from askwell.core.intent import Intent
from askwell.core.registry import Registry
from askwell.core.sqlbuild import build
from askwell.core.validate import ValidationResult, validate
from askwell.pipeline.prompt import system_prompt
from tests.core.conftest import NOW, make_registry

ROLES_OFF = ALL - {"link_roles"}


def _check(
    registry: Registry, intent: dict[str, Any], features: frozenset[str] = ALL
) -> ValidationResult:
    return validate(Intent.model_validate(intent), registry, now=NOW, features=features)


def _two_links() -> Registry:
    return make_registry(
        {"flights": ["origin_id", "dest_id"], "airports": ["elevation"]},
        [("flights", "origin_id", "airports", "id"), ("flights", "dest_id", "airports", "id")],
    )


AIRPORTS = {"intent_type": "summary", "entity": "airports", "metrics": [{"agg": "count"}]}


def test_a_named_link_in_has_is_refused_with_link_roles_off() -> None:
    named = {**AIRPORTS, "filters": [{"has": "flights@origin_id"}]}
    assert _check(_two_links(), named).ok
    assert _check(_two_links(), named, ROLES_OFF).codes == ["feature_off"]


def test_with_link_roles_off_the_has_refusal_does_not_teach_named_links() -> None:
    plain = {**AIRPORTS, "filters": [{"has": "flights"}]}
    result = _check(_two_links(), plain, ROLES_OFF)
    assert result.codes == ["ambiguous_path"]
    assert all("@" not in issue.message for issue in result.issues)
    on = _check(_two_links(), plain)
    assert any("flights@origin_id" in issue.message for issue in on.issues)


def test_the_prompt_teaches_named_has_links_only_with_link_roles_on() -> None:
    assert '"entity@link"' in system_prompt(ALL)
    assert '"entity@link"' not in system_prompt(ROLES_OFF)
    assert '{"has": <entity>' in system_prompt(ROLES_OFF)


# Twice an integer, below 2.4: true only for 1. Rounded to 2, the threshold would
# drop every row.
DOUBLED_UNDER = {
    "intent_type": "summary",
    "entity": "work_order_parts",
    "metrics": [{"agg": "count"}],
    "filters": [
        {"field": {"op": "add", "left": "quantity", "right": "quantity"}, "op": "lt", "value": 2.4}
    ],
}


@pytest.mark.parametrize("engine_name", ["postgresql", "sqlite"])
def test_integer_arithmetic_keeps_fractions(
    engine_name: str, registry: Registry, pg_seeded: Engine, sqlite_ro: Engine
) -> None:
    with pg_seeded.connect() as conn:
        expected = conn.execute(
            text("SELECT count(*) FROM work_order_parts WHERE quantity = 1")
        ).scalar_one()
    assert expected > 0
    plan = _check(registry, DOUBLED_UNDER).plan
    assert plan is not None
    engine = pg_seeded if engine_name == "postgresql" else sqlite_ro
    assert run(engine, build(plan)).rows == [(expected,)]


PRODUCT = {"op": "multiply", "left": "quantity", "right": "parts.unit_price"}


def test_a_computed_alias_cannot_name_a_field(registry: Registry) -> None:
    shadow = {
        "intent_type": "row_list",
        "entity": "work_order_parts",
        "select": ["quantity", {**PRODUCT, "alias": "quantity"}],
        "order_by": [{"target": "quantity", "direction": "desc"}],
    }
    assert _check(registry, shadow).codes == ["alias_collision"]
    unselected = {**shadow, "select": [{**PRODUCT, "alias": "part_id"}]}
    assert _check(registry, unselected).codes == ["alias_collision"]


def test_two_computed_values_cannot_share_a_name(registry: Registry) -> None:
    twice = {
        "intent_type": "row_list",
        "entity": "work_order_parts",
        "select": [
            {**PRODUCT, "alias": "line_total"},
            {"op": "add", "left": "quantity", "right": "quantity", "alias": "line_total"},
        ],
    }
    assert _check(registry, twice).codes == ["duplicate_alias"]
    fine = {**twice, "select": [{**PRODUCT, "alias": "line_total"}, "quantity"]}
    assert _check(registry, fine).ok
