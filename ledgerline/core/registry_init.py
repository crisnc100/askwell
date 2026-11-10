"""`registry init`: draft a registry from a live database.

- Introspection uses the SQLAlchemy inspector (tables and views, columns, primary keys,
  single-column foreign keys to a single-column primary key).
- Without a declared foreign key, `<x>_id` (or a column named exactly like another
  table's primary key) pointing at a single-column primary key becomes an `inferred`
  relationship.
- Fields whose names look sensitive are hidden. Nothing reads data unless
  `include_values` is set; then short text fields that are not name-like become
  categorical with their distinct values.
- The output is marked `draft: true`, and a role that can write is reported.
- Same database in, byte-identical YAML out.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Engine,
    Float,
    Integer,
    Numeric,
    column,
    func,
    inspect,
    select,
    table,
    text,
)

from ledgerline.core.registry import (
    NUMERIC_TYPES,
    TEMPORAL_TYPES,
    EntityDef,
    FieldDef,
    FieldType,
    Registry,
    Relationship,
    slugify,
)

SENSITIVE = re.compile(r"password|hash|token|secret|ssn|email|phone", re.IGNORECASE)
NAME_LIKE = re.compile(r"name|title|desc|comment|note|address|street|url", re.IGNORECASE)
MAX_CATEGORICAL = 50
_ID_SUFFIX = re.compile(r"^(.+?)_?id$", re.IGNORECASE)


@dataclass
class InitResult:
    registry: Registry
    warnings: list[str] = field(default_factory=list[str])


def field_type(sa_type: Any) -> FieldType:
    """Map a reflected SQLAlchemy type to a registry type. Unknown types are text."""
    if isinstance(sa_type, Boolean):
        return "boolean"
    if isinstance(sa_type, Integer):
        return "integer"
    if isinstance(sa_type, Numeric | Float):
        return "number"
    if isinstance(sa_type, DateTime):
        return "datetime"
    if isinstance(sa_type, Date):
        return "date"
    return "text"


def _unique_slugs(names: list[str]) -> dict[str, str]:
    """Real name -> slug, with `_2`, `_3` suffixes on collisions, in the given order."""
    out: dict[str, str] = {}
    used: set[str] = set()
    for name in names:
        base = slugify(name)
        slug, n = base, 2
        while slug in used:
            slug, n = f"{base}_{n}", n + 1
        used.add(slug)
        out[name] = slug
    return out


@dataclass
class _Table:
    name: str
    kind: str
    columns: list[dict[str, Any]]
    pk: list[str]
    fks: list[dict[str, Any]]


def _read_tables(engine: Engine) -> list[_Table]:
    insp = inspect(engine)
    names = [(n, "table") for n in insp.get_table_names()]
    names += [(n, "view") for n in insp.get_view_names()]
    tables: list[_Table] = []
    for name, kind in sorted(names):
        if name.startswith("sqlite_"):
            continue
        tables.append(
            _Table(
                name=name,
                kind=kind,
                columns=[dict(c) for c in insp.get_columns(name)],
                pk=list(insp.get_pk_constraint(name).get("constrained_columns") or []),
                fks=[dict(fk) for fk in insp.get_foreign_keys(name)] if kind == "table" else [],
            )
        )
    return tables


def _relationships(
    tables: list[_Table],
    entity_slug: dict[str, str],
    field_slugs: dict[str, dict[str, str]],
    warnings: list[str],
) -> list[Relationship]:
    by_lower = {t.name.lower(): t for t in tables}
    single_pk = {t.name: t.pk[0] for t in tables if len(t.pk) == 1}
    rels: dict[tuple[str, str], Relationship] = {}
    skipped: set[tuple[str, str]] = set()  # (table, lowercased column) of skipped keys

    for t in tables:
        for fk in t.fks:
            src_cols = list(fk.get("constrained_columns") or [])
            dst_cols = list(fk.get("referred_columns") or [])
            target = by_lower.get(str(fk.get("referred_table") or "").lower())
            if len(src_cols) != 1 or len(dst_cols) != 1 or target is None:
                warnings.append(f"skipped foreign key on {t.name}: not single-column or unknown")
                skipped.update((t.name, c.lower()) for c in src_cols)
                continue
            dst_col = next(
                (c for c in field_slugs[target.name] if c.lower() == dst_cols[0].lower()), None
            )
            src_col = next(
                (c for c in field_slugs[t.name] if c.lower() == src_cols[0].lower()), None
            )
            if dst_col is None or src_col is None or single_pk.get(target.name) != dst_col:
                warnings.append(
                    f"skipped foreign key {t.name}.{src_cols[0]}: target is not a primary key"
                )
                skipped.add((t.name, src_cols[0].lower()))
                continue
            key = (t.name, src_col)
            rels.setdefault(
                key,
                Relationship(
                    from_entity=entity_slug[t.name],
                    from_field=field_slugs[t.name][src_col],
                    to_entity=entity_slug[target.name],
                    to_field=field_slugs[target.name][dst_col],
                    source="declared",
                ),
            )

    pk_owner: dict[str, list[str]] = {}
    for name, pk in single_pk.items():
        if pk.lower() != "id":
            pk_owner.setdefault(pk.lower(), []).append(name)

    for t in tables:
        for col in t.columns:
            col_name = str(col["name"])
            # A declared key that was skipped says where the column points; guessing a
            # different target from its name would invent a wrong join.
            if (t.name, col_name) in rels or t.pk == [col_name]:
                continue
            if (t.name, col_name.lower()) in skipped:
                continue
            candidates: list[str] = []
            match = _ID_SUFFIX.match(col_name)
            if match:
                stem = match.group(1).lower()
                for guess in (stem, f"{stem}s", f"{stem}es"):
                    target = by_lower.get(guess)
                    if target is not None and target.name in single_pk and target.name != t.name:
                        candidates.append(target.name)
            for owner in pk_owner.get(col_name.lower(), []):
                if owner != t.name and owner not in candidates:
                    candidates.append(owner)
            if len(candidates) != 1:
                if len(candidates) > 1:
                    warnings.append(f"{t.name}.{col_name}: several inferred targets, none kept")
                continue
            target_name = candidates[0]
            rels[(t.name, col_name)] = Relationship(
                from_entity=entity_slug[t.name],
                from_field=field_slugs[t.name][col_name],
                to_entity=entity_slug[target_name],
                to_field=field_slugs[target_name][single_pk[target_name]],
                source="inferred",
            )
    return sorted(rels.values(), key=lambda r: (r.from_entity, r.from_field, r.to_entity))


def _categorical_values(engine: Engine, t: _Table, col_name: str) -> list[str] | None:
    ref = table(t.name, column(col_name))
    col = ref.c[col_name]
    with engine.connect() as conn:
        distinct, non_null = conn.execute(
            select(func.count(col.distinct()), func.count(col)).select_from(ref)
        ).one()
        if not 0 < distinct <= MAX_CATEGORICAL:
            return None
        if distinct == non_null and non_null > 5:
            return None  # one value per row: an identifier, not a category
        rows = conn.execute(select(col).where(col.is_not(None)).distinct().order_by(col))
        return sorted({str(row[0]) for row in rows})


def write_privilege_warning(
    engine: Engine, table_names: list[str], sqlite_path: str | None = None
) -> str | None:
    """A warning when the connecting identity could write. Ledgerline never writes, but a
    SELECT-only role is the defence that does not depend on Ledgerline being right."""
    dialect = engine.dialect.name
    if dialect == "sqlite":
        if sqlite_path is not None and os.access(Path(sqlite_path), os.W_OK):
            return "the SQLite file is writable by this user; Ledgerline opens it read-only"
        return None
    if dialect == "postgresql":
        writable: list[str] = []
        with engine.connect() as conn:
            for name in table_names:
                can_write = conn.execute(
                    text(
                        "SELECT has_table_privilege(current_user, quote_ident(:t), "
                        "'INSERT,UPDATE,DELETE,TRUNCATE')"
                    ),
                    {"t": name},
                ).scalar_one()
                if can_write:
                    writable.append(name)
        if writable:
            return (
                f"role can write to {len(writable)} table(s) (e.g. {writable[0]}); "
                "use a SELECT-only role"
            )
        return None
    return f"cannot check write privileges on {dialect}"


def init_registry(
    engine: Engine,
    *,
    include_values: bool = False,
    name: str = "",
    sqlite_path: str | None = None,
) -> InitResult:
    tables = _read_tables(engine)
    warnings: list[str] = []
    entity_slug = _unique_slugs([t.name for t in tables])
    field_slugs = {t.name: _unique_slugs([str(c["name"]) for c in t.columns]) for t in tables}
    relationships = _relationships(tables, entity_slug, field_slugs, warnings)
    key_columns = {(r.from_entity, r.from_field) for r in relationships}

    entities: dict[str, EntityDef] = {}
    for t in tables:
        slug = entity_slug[t.name]
        fields: dict[str, FieldDef] = {}
        for col in t.columns:
            col_name = str(col["name"])
            fslug = field_slugs[t.name][col_name]
            ftype = field_type(col["type"])
            hidden = bool(SENSITIVE.search(col_name))
            is_key = (
                col_name in t.pk or (slug, fslug) in key_columns or bool(_ID_SUFFIX.match(col_name))
            )
            allowed: list[str] = []
            if include_values and ftype == "text" and not hidden and not NAME_LIKE.search(col_name):
                allowed = _categorical_values(engine, t, col_name) or []
            fields[fslug] = FieldDef(
                column=col_name,
                type=ftype,
                filterable=not hidden,
                aggregatable=ftype in (NUMERIC_TYPES | TEMPORAL_TYPES)
                and not is_key
                and not hidden,
                hidden=hidden,
                categorical=bool(allowed),
                allowed_values=allowed,
            )
        entities[slug] = EntityDef(
            table=t.name,
            kind="view" if t.kind == "view" else "table",
            primary_key=[field_slugs[t.name][c] for c in t.pk if c in field_slugs[t.name]],
            fields=fields,
        )
    warning = write_privilege_warning(
        engine, [t.name for t in tables if t.kind == "table"], sqlite_path
    )
    if warning:
        warnings.append(warning)
    registry = Registry(
        schema_version=1,
        draft=True,
        name=name,
        entities=entities,
        relationships=relationships,
    )
    return InitResult(registry, warnings)
