"""The registry model: slugs, load/dump round trip, and the invariants it enforces."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from ledgerline.core.registry import (
    EntityDef,
    FieldDef,
    Registry,
    dump_registry,
    load_registry,
    slugify,
)
from tests.core.conftest import FIELDSERVICE_REGISTRY


@pytest.mark.parametrize(
    ("name", "slug"),
    [
        ("work_orders", "work_orders"),
        ("Order Lines", "order_lines"),
        ("Unit.Price", "unit_price"),
        ("  --weird--  ", "weird"),
        ("2019 sales", "x_2019_sales"),
        ("ÄÖÜ", "x"),
        ("CamelCase", "camelcase"),
    ],
)
def test_slugify(name: str, slug: str) -> None:
    assert slugify(name) == slug


def test_round_trip_is_byte_identical(tmp_path: Path) -> None:
    registry = load_registry(FIELDSERVICE_REGISTRY)
    text = dump_registry(registry)
    path = tmp_path / "r.yaml"
    path.write_text(text)
    assert dump_registry(load_registry(path)) == text
    assert load_registry(path) == registry


def test_fieldservice_registry_hides_sensitive_fields() -> None:
    users = load_registry(FIELDSERVICE_REGISTRY).entities["users"].fields
    assert users["email"].hidden
    assert users["password_hash"].hidden
    assert not load_registry(FIELDSERVICE_REGISTRY).draft


def _field(**kw: Any) -> FieldDef:
    return FieldDef(column="c", type="text", **kw)


def test_allowed_values_need_categorical() -> None:
    with pytest.raises(ValidationError, match="categorical"):
        _field(allowed_values=["a"])


def test_hidden_fields_cannot_be_categorical() -> None:
    with pytest.raises(ValidationError, match="hidden"):
        _field(hidden=True, categorical=True)


def test_value_aliases_must_point_at_allowed_values() -> None:
    with pytest.raises(ValidationError, match="unknown"):
        _field(categorical=True, allowed_values=["a"], value_aliases={"A!": "b"})


def _registry(**kw: Any) -> Registry:
    return Registry.model_validate({"schema_version": 1, "draft": False, **kw})


def test_slugs_must_be_registry_safe() -> None:
    entity = EntityDef(table="t", fields={"ok": _field()}).model_dump()
    with pytest.raises(ValidationError, match="entity slug"):
        _registry(entities={"Bad Name": entity})
    bad_field = {**entity, "fields": {"Bad.Field": _field().model_dump()}}
    with pytest.raises(ValidationError, match="field slug"):
        _registry(entities={"t": bad_field})


def test_primary_key_must_be_a_field() -> None:
    entity = EntityDef(table="t", fields={"a": _field()}).model_dump()
    with pytest.raises(ValidationError, match="primary key"):
        _registry(entities={"t": {**entity, "primary_key": ["missing"]}})


def test_relationships_must_reference_fields() -> None:
    entity = EntityDef(table="t", fields={"a": _field()}).model_dump()
    with pytest.raises(ValidationError, match="unknown field"):
        _registry(
            entities={"t": entity},
            relationships=[
                {
                    "from_entity": "t",
                    "from_field": "a",
                    "to_entity": "u",
                    "to_field": "id",
                    "source": "declared",
                }
            ],
        )


def test_unknown_keys_are_rejected() -> None:
    with pytest.raises(ValidationError, match="extra"):
        _registry(entities={}, sql="SELECT 1")
