"""Confirm: the drafted registry for a workspace, and the person's edits to it.

After a set loads, `registry init` drafts a registry from the workspace's SQLite file.
Only the links Check found are kept, so the registry joins exactly what Prepare-your-data
promised. Fields whose names look sensitive start hidden.

Category values are opt-in. The draft keeps each short text column's distinct values to
one side; a column's values go into the registry (and so to the model) only when the
person ticks "Share these values with the model". An unshared column is a plain text
field: the model never sees its values, and the validator accepts any value typed, so a
person who types one still gets an answer.

The person can hide or unhide a field and give it a description. Applying the edits
gives the registry that Confirm saves (`draft: false`).
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.engine import Engine

from askwell.core.executor import readonly_engine
from askwell.core.features import ALL, Features
from askwell.core.registry import (
    NUMERIC_TYPES,
    TEMPORAL_TYPES,
    EntityDef,
    FieldDef,
    Registry,
    dump_registry,
    load_registry,
)
from askwell.core.registry_init import init_registry
from askwell.workspace.check import TablePlan
from askwell.workspace.store import (
    DRAFT_FILE,
    FIELDS_FILE,
    Workspace,
    WorkspaceError,
    WorkspaceStore,
    WrongStateError,
)

MAX_DESCRIPTION = 300


class FieldEdit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hidden: bool | None = None
    description: str | None = Field(default=None, max_length=MAX_DESCRIPTION)
    share_values: bool | None = None


class Edits(BaseModel):
    """Field edits keyed by `entity.field`, and each table's name column keyed by table:
    a field name, or null for none. A table left out keeps the drafted name column."""

    model_config = ConfigDict(extra="forbid")

    fields: dict[str, FieldEdit] = Field(default_factory=dict[str, FieldEdit])
    labels: dict[str, str | None] = Field(default_factory=dict[str, str | None])


@dataclass
class FieldInfo:
    """What the draft knows beyond the registry: each field's original header, the
    category values held back from the model, and the fields hidden automatically."""

    headers: dict[str, str] = field(default_factory=dict[str, str])
    values: dict[str, list[str]] = field(default_factory=dict[str, list[str]])
    auto_hidden: list[str] = field(default_factory=list[str])

    @classmethod
    def from_json(cls, text: str) -> FieldInfo:
        return cls(**json.loads(text))

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2)


def draft(db_path: Path, plans: list[TablePlan], features: Features = ALL) -> dict[str, str]:
    """Draft the registry for a freshly loaded database. Returns the draft files by
    name, for the store to swap in with the database."""
    engine: Engine = readonly_engine(f"sqlite:///{db_path}")
    try:
        result = init_registry(engine, include_values=True, features=features)
    finally:
        engine.dispose()
    found = {(p.name, link.column) for p in plans for link in p.links}
    relationships = [
        r
        for r in result.registry.relationships
        if r.source == "declared" and (r.from_entity, r.from_field) in found
    ]
    info = FieldInfo()
    headers = {(p.name, c.name): c.header for p in plans for c in p.columns}
    entities: dict[str, EntityDef] = {}
    for slug, entity in result.registry.entities.items():
        fields: dict[str, FieldDef] = {}
        for name, fdef in entity.fields.items():
            key = f"{slug}.{name}"
            info.headers[key] = headers.get((entity.table, fdef.column), fdef.column)
            if fdef.hidden:
                info.auto_hidden.append(key)
            if fdef.allowed_values:
                info.values[key] = list(fdef.allowed_values)
            fields[name] = _with(fdef, categorical=False, allowed_values=[])
        entities[slug] = entity.model_copy(update={"fields": fields})
    registry = Registry(
        schema_version=1,
        draft=True,
        entities=entities,
        relationships=relationships,
    )
    return {DRAFT_FILE: dump_registry(registry), FIELDS_FILE: info.to_json()}


def load_draft(workspace: Workspace) -> tuple[Registry, FieldInfo]:
    if not workspace.draft_path.exists():
        raise WorkspaceError("Check your files first.")
    info = FieldInfo.from_json(workspace.fields_path.read_text(encoding="utf-8"))
    return load_registry(workspace.draft_path), info


def saved_edits(workspace: Workspace) -> Edits:
    if not workspace.edits_path.exists():
        return Edits()
    return Edits.model_validate_json(workspace.edits_path.read_text(encoding="utf-8"))


def _with(fdef: FieldDef, **changes: Any) -> FieldDef:
    return FieldDef.model_validate({**fdef.model_dump(), **changes})


def _is_key(registry: Registry, entity: str, name: str) -> bool:
    if name in registry.entities[entity].primary_key:
        return True
    if any(r.from_entity == entity and r.from_field == name for r in registry.relationships):
        return True
    return name == "id" or name.endswith("_id")


def label_options(registry: Registry, entity: str) -> list[str]:
    """The fields that can name a row of `entity`: its text fields other than keys and
    links, when it has a single-field key."""
    edef = registry.entities[entity]
    if len(edef.primary_key) != 1:
        return []
    return [
        name
        for name, fdef in edef.fields.items()
        if fdef.type == "text" and not _is_key(registry, entity, name)
    ]


def apply(registry: Registry, info: FieldInfo, edits: Edits) -> Registry:
    """The registry with `edits` applied, marked confirmed (`draft: false`). A hidden
    field never names a row: hiding the name column leaves the table without one."""
    for key in edits.fields:
        entity, _, name = key.partition(".")
        if entity not in registry.entities or name not in registry.entities[entity].fields:
            raise WorkspaceError(f"There is no field {key!r} in this workspace.")
    for entity, label in edits.labels.items():
        if entity not in registry.entities:
            raise WorkspaceError(f"There is no table {entity!r} in this workspace.")
        if label is not None and label not in label_options(registry, entity):
            raise WorkspaceError(f"The field {entity}.{label} cannot name a row of {entity}.")
    entities: dict[str, EntityDef] = {}
    for slug, entity in registry.entities.items():
        fields: dict[str, FieldDef] = {}
        for name, fdef in entity.fields.items():
            key = f"{slug}.{name}"
            edit = edits.fields.get(key, FieldEdit())
            hidden = fdef.hidden if edit.hidden is None else edit.hidden
            description = fdef.description if edit.description is None else edit.description
            share = bool(edit.share_values) and not hidden
            if edit.share_values and key not in info.values:
                raise WorkspaceError(f"The field {key!r} has no category values to share.")
            values = info.values.get(key, []) if share else []
            fields[name] = _with(
                fdef,
                hidden=hidden,
                description=" ".join(description.split()),
                filterable=not hidden,
                aggregatable=not hidden
                and fdef.type in (NUMERIC_TYPES | TEMPORAL_TYPES)
                and not _is_key(registry, slug, name),
                categorical=bool(values),
                allowed_values=values,
            )
        label = edits.labels.get(slug, entity.label)
        if label is not None and fields[label].hidden:
            label = None
        entities[slug] = EntityDef.model_validate(
            {**entity.model_dump(), "fields": fields, "label": label}
        )
    return Registry(
        schema_version=1,
        draft=False,
        name=registry.name,
        entities=entities,
        relationships=registry.relationships,
    )


def field_rows(registry: Registry, info: FieldInfo, edits: Edits) -> list[dict[str, Any]]:
    """What the Confirm page lists: one entry per table, with its fields and links."""
    applied = apply(registry, info, edits)
    links = {
        (r.from_entity, r.from_field): f"{r.to_entity}.{r.to_field}" for r in applied.relationships
    }
    tables: list[dict[str, Any]] = []
    for slug, entity in applied.entities.items():
        rows: list[dict[str, Any]] = []
        for name, fdef in entity.fields.items():
            key = f"{slug}.{name}"
            rows.append(
                {
                    "key": key,
                    "name": name,
                    "header": info.headers.get(key, name),
                    "type": fdef.type,
                    "hidden": fdef.hidden,
                    "auto_hidden": key in info.auto_hidden,
                    "description": fdef.description,
                    "values": info.values.get(key, []),
                    "share_values": fdef.categorical,
                    "link": links.get((slug, name)),
                }
            )
        tables.append(
            {
                "name": slug,
                "fields": rows,
                "label": entity.label,
                "label_options": [
                    name for name in label_options(applied, slug) if not entity.fields[name].hidden
                ],
            }
        )
    return tables


def normalized(registry: Registry, edits: Edits) -> Edits:
    """The edits as they take effect: a hidden field never shares its values. Saving
    this form means the page, the preview and the registry all read the same thing."""
    out: dict[str, FieldEdit] = {}
    for key, edit in edits.fields.items():
        entity, _, name = key.partition(".")
        hidden = edit.hidden
        if hidden is None:
            hidden = registry.entities[entity].fields[name].hidden
        share = edit.share_values
        if hidden and share:
            share = False
        out[key] = edit.model_copy(update={"share_values": share})
    return Edits(fields=out, labels=dict(edits.labels))


def confirm(store: WorkspaceStore, workspace: Workspace, edits: Edits) -> Registry:
    """Save the edited registry and move to `confirmed`. A confirmed workspace can be
    confirmed again with new edits; its files stay fixed."""
    with store.locked(workspace.id) as fresh:
        if fresh.meta.state == "new":
            raise WrongStateError("Check your files first.")
        registry, info = load_draft(fresh)
        applied = apply(registry, info, edits)
        kept = normalized(registry, edits)
        store.write_counted_together(
            [
                (fresh.registry_path, dump_registry(applied).encode("utf-8")),
                (fresh.edits_path, kept.model_dump_json(indent=2).encode("utf-8")),
            ]
        )
        fresh.meta.state = "confirmed"
    return applied
