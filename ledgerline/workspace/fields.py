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
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.engine import Engine

from ledgerline.core.executor import readonly_engine
from ledgerline.core.registry import (
    NUMERIC_TYPES,
    TEMPORAL_TYPES,
    EntityDef,
    FieldDef,
    Registry,
    dump_registry,
    load_registry,
)
from ledgerline.core.registry_init import init_registry
from ledgerline.workspace.check import TablePlan
from ledgerline.workspace.store import Workspace, WorkspaceError, WorkspaceStore, WrongStateError

MAX_DESCRIPTION = 300


class FieldEdit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hidden: bool | None = None
    description: str | None = Field(default=None, max_length=MAX_DESCRIPTION)
    share_values: bool | None = None


class Edits(BaseModel):
    """Edits keyed by `entity.field`."""

    model_config = ConfigDict(extra="forbid")

    fields: dict[str, FieldEdit] = Field(default_factory=dict[str, FieldEdit])


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


def draft(workspace: Workspace, plans: list[TablePlan]) -> Registry:
    """Draft the registry for a freshly loaded workspace and save it as the draft."""
    engine: Engine = readonly_engine(f"sqlite:///{workspace.db_path}")
    try:
        result = init_registry(engine, include_values=True)
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
    workspace.draft_path.write_text(dump_registry(registry), encoding="utf-8")
    workspace.fields_path.write_text(info.to_json(), encoding="utf-8")
    return registry


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


def apply(registry: Registry, info: FieldInfo, edits: Edits) -> Registry:
    """The registry with `edits` applied, marked confirmed (`draft: false`)."""
    for key in edits.fields:
        entity, _, name = key.partition(".")
        if entity not in registry.entities or name not in registry.entities[entity].fields:
            raise WorkspaceError(f"There is no field {key!r} in this workspace.")
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
        entities[slug] = entity.model_copy(update={"fields": fields})
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
        tables.append({"name": slug, "fields": rows})
    return tables


def confirm(store: WorkspaceStore, workspace: Workspace, edits: Edits) -> Registry:
    """Save the edited registry and move to `confirmed`. A confirmed workspace can be
    confirmed again with new edits; its files stay fixed."""
    if workspace.meta.state == "new":
        raise WrongStateError("Check your files first.")
    with store.lock(workspace.id):
        registry, info = load_draft(workspace)
        applied = apply(registry, info, edits)
        workspace.registry_path.write_text(dump_registry(applied), encoding="utf-8")
        workspace.edits_path.write_text(edits.model_dump_json(indent=2), encoding="utf-8")
        workspace.meta.state = "confirmed"
        workspace.save()
    return applied
