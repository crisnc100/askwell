from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import Engine

from askwell.config import get_settings
from askwell.core.executor import readonly_engine
from askwell.core.intent import Intent
from askwell.core.registry import (
    EntityDef,
    FieldDef,
    Registry,
    Relationship,
    load_registry,
)
from askwell.core.validate import ValidationResult, validate

ROOT = Path(__file__).resolve().parents[2]
FIELDSERVICE_REGISTRY = ROOT / "registries" / "fieldservice.yaml"
NOW: datetime = get_settings().now


@pytest.fixture(scope="session")
def registry() -> Registry:
    return load_registry(FIELDSERVICE_REGISTRY)


@pytest.fixture(scope="session")
def sqlite_ro(sqlite_fieldservice: Engine) -> Iterator[Engine]:
    """The fieldservice SQLite fixture, opened read-only the way the executor opens it."""
    engine = readonly_engine(str(sqlite_fieldservice.url))
    yield engine
    engine.dispose()


def check(registry: Registry, row_cap: int = 1000, **intent: Any) -> ValidationResult:
    return validate(Intent.model_validate(intent), registry, now=NOW, row_cap=row_cap)


def make_registry(
    entities: dict[str, list[str]],
    relationships: list[tuple[str, str, str, str]],
    draft: bool = False,
) -> Registry:
    """Compact synthetic registry: every entity gets an integer `id` plus the named
    integer fields; relationships are (from_entity, from_field, to_entity, to_field)."""
    return Registry(
        schema_version=1,
        draft=draft,
        entities={
            name: EntityDef(
                table=name,
                primary_key=["id"],
                fields={
                    "id": FieldDef(column="id", type="integer"),
                    **{f: FieldDef(column=f, type="integer", aggregatable=True) for f in fields},
                },
            )
            for name, fields in entities.items()
        },
        relationships=[
            Relationship(from_entity=a, from_field=b, to_entity=c, to_field=d, source="declared")
            for a, b, c, d in relationships
        ],
    )
