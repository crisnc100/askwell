"""The registry: what a schema exposes to Askwell, and nothing more.

Entities are DB tables or views only; there is no SQL in the YAML. Every name the
model may use is a registry-safe slug that maps to a real identifier, so spaces,
dots and mixed case in real schemas never reach SQL text unquoted.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Literal, Self

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

FieldType = Literal["integer", "number", "text", "boolean", "date", "datetime"]
NUMERIC_TYPES: frozenset[str] = frozenset({"integer", "number"})
TEMPORAL_TYPES: frozenset[str] = frozenset({"date", "datetime"})

_SLUG = re.compile(r"^[a-z][a-z0-9_]*$")


def slugify(name: str) -> str:
    """Lowercase, non-alphanumerics to `_`, collapsed; a leading digit gets a prefix."""
    slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    if not slug:
        slug = "x"
    if not slug[0].isalpha():
        slug = f"x_{slug}"
    return slug


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class FieldDef(_Strict):
    column: str  # the real column identifier
    type: FieldType
    description: str = ""
    aliases: list[str] = Field(default_factory=list[str])
    filterable: bool = True
    # sum / avg / min / max. count and count_distinct work on any visible field.
    aggregatable: bool = False
    hidden: bool = False
    categorical: bool = False
    allowed_values: list[str] = Field(default_factory=list[str])
    # alias (case-insensitive) -> canonical allowed value
    value_aliases: dict[str, str] = Field(default_factory=dict[str, str])

    @model_validator(mode="after")
    def _check(self) -> Self:
        if self.allowed_values and not self.categorical:
            raise ValueError(f"{self.column}: allowed_values need categorical: true")
        if self.hidden and self.categorical:
            raise ValueError(f"{self.column}: a hidden field cannot be categorical")
        for alias, target in self.value_aliases.items():
            if target not in self.allowed_values:
                raise ValueError(f"{self.column}: value alias {alias!r} -> unknown {target!r}")
        return self


class EntityDef(_Strict):
    table: str  # the real table or view identifier
    db_schema: str | None = None
    kind: Literal["table", "view"] = "table"
    description: str = ""
    aliases: list[str] = Field(default_factory=list[str])
    primary_key: list[str] = Field(default_factory=list[str])  # field slugs
    fields: dict[str, FieldDef]


class Relationship(_Strict):
    """`from_entity.from_field` (the many side) references `to_entity.to_field` (one)."""

    from_entity: str
    from_field: str
    to_entity: str
    to_field: str
    cardinality: Literal["many_to_one"] = "many_to_one"
    source: Literal["declared", "inferred"]


class Registry(_Strict):
    schema_version: Literal[1]
    draft: bool
    name: str = ""
    entities: dict[str, EntityDef]
    relationships: list[Relationship] = Field(default_factory=list[Relationship])

    @model_validator(mode="after")
    def _check(self) -> Self:
        for slug, entity in self.entities.items():
            if not _SLUG.match(slug):
                raise ValueError(f"entity slug {slug!r} is not registry-safe")
            for field_slug in entity.fields:
                if not _SLUG.match(field_slug):
                    raise ValueError(f"field slug {slug}.{field_slug} is not registry-safe")
            for key in entity.primary_key:
                if key not in entity.fields:
                    raise ValueError(f"{slug}: primary key {key!r} is not a field")
        for rel in self.relationships:
            for entity_slug, field_slug in (
                (rel.from_entity, rel.from_field),
                (rel.to_entity, rel.to_field),
            ):
                entity = self.entities.get(entity_slug)
                if entity is None or field_slug not in entity.fields:
                    raise ValueError(
                        f"relationship references unknown field {entity_slug}.{field_slug}"
                    )
        return self


def load_registry(path: Path | str) -> Registry:
    with Path(path).open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    return Registry.model_validate(data)


def dump_registry(registry: Registry) -> str:
    """Deterministic YAML: model field order, entities and relationships as given."""
    data = registry.model_dump(mode="json")
    return yaml.safe_dump(data, sort_keys=False, allow_unicode=True, width=100)
