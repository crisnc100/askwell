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

# Text that stands for "no value" in a column of numbers stored as text, compared after
# trimming. `registry init` skips it when deciding a column holds numbers; the SQL
# builder reads it as NULL.
TEXT_NUMBER_PLACEHOLDERS: tuple[str, ...] = (
    "",
    "null",
    "NULL",
    "Null",
    "N/A",
    "n/a",
    "NA",
    "na",
    "-",
)


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
    # A number stored in a text column (`registry init`'s numeric_text): read through a
    # cast, with placeholder text such as 'null' read as NULL.
    text_number: bool = False

    @model_validator(mode="after")
    def _check(self) -> Self:
        if self.allowed_values and not self.categorical:
            raise ValueError(f"{self.column}: allowed_values need categorical: true")
        if self.hidden and self.categorical:
            raise ValueError(f"{self.column}: a hidden field cannot be categorical")
        if self.text_number and self.type != "number":
            raise ValueError(f"{self.column}: text_number needs type: number")
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
    # The field that names one row ("the name of the thing"). Grouping by it groups by
    # the key as well, so two customers that share a name stay two rows.
    label: str | None = None
    fields: dict[str, FieldDef]

    @model_validator(mode="after")
    def _check_label(self) -> Self:
        if self.label is None:
            return self
        if self.label not in self.fields:
            raise ValueError(f"{self.table}: label {self.label!r} is not a field")
        if len(self.primary_key) != 1:
            raise ValueError(f"{self.table}: a label needs a single-field primary key")
        if self.label == self.primary_key[0]:
            raise ValueError(f"{self.table}: the label cannot be the primary key")
        if self.fields[self.label].hidden:
            raise ValueError(f"{self.table}: the label {self.label!r} is hidden")
        return self


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
    for entity in data["entities"].values():
        # Written only when set, so a registry without them dumps as it did before they
        # existed (Spider registries are checked against committed hashes).
        if entity["label"] is None:
            del entity["label"]
        for fdef in entity["fields"].values():
            if not fdef["text_number"]:
                del fdef["text_number"]
    return yaml.safe_dump(data, sort_keys=False, allow_unicode=True, width=100)
