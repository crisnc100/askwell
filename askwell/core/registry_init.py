"""`registry init`: draft a registry from a live database.

- Introspection uses the SQLAlchemy inspector (tables and views, columns, primary keys,
  single-column foreign keys to a single-column primary key, or, with `inferred_links`
  on, to a single-column unique column).
- Without a declared foreign key, `<x>_id` (or a column named exactly like another
  table's primary key) pointing at a single-column primary key becomes an `inferred`
  relationship. With `inferred_links` on, a column named after a table (`airline`,
  `origin_airport_id`) links to it too, but only on evidence read from the data: at
  least MIN_DISTINCT_FOR_LINK distinct values, every one of them that table's key.
- With `numeric_text` on, a text column whose every value reads as a number (blank and
  'null'-like placeholders aside) is drafted as a number, marked `text_number` so the
  builder casts it. Leading zeros and id, code, zip, postal or phone names stay text.
- Fields whose names look sensitive are hidden. Values are read for the two checks
  above; beyond them nothing reads data unless `include_values` is set, and then short
  text fields that are not name-like become categorical with their distinct values.
- The output is marked `draft: true`, and a role that can write is reported.
- Same database in, byte-identical YAML out.
"""

from __future__ import annotations

import os
import re
from collections.abc import Sequence
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
from sqlalchemy.exc import OperationalError

from askwell.core.features import ALL, Features
from askwell.core.registry import (
    NUMERIC_TYPES,
    TEMPORAL_TYPES,
    TEXT_NUMBER_PLACEHOLDERS,
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
    unique: set[str] = field(default_factory=set[str])  # single-column unique columns


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
                unique=_unique_columns(insp, name) if kind == "table" else set(),
            )
        )
    return tables


def _unique_columns(insp: Any, name: str) -> set[str]:
    found = [list(u.get("column_names") or []) for u in insp.get_unique_constraints(name)]
    found += [list(i.get("column_names") or []) for i in insp.get_indexes(name) if i.get("unique")]
    return {str(cols[0]) for cols in found if len(cols) == 1}


def _find(names: list[str], wanted: str, case_insensitive: bool) -> str | None:
    """The identifier `wanted` among `names`: exact match first. Only where identifiers
    are case-insensitive (SQLite) may a unique case-insensitive match stand in."""
    if wanted in names:
        return wanted
    if case_insensitive:
        folded = [n for n in names if n.lower() == wanted.lower()]
        if len(folded) == 1:
            return folded[0]
    return None


def _relationships(
    tables: list[_Table],
    entity_slug: dict[str, str],
    field_slugs: dict[str, dict[str, str]],
    warnings: list[str],
    *,
    default_schema: str | None = None,
    case_insensitive: bool = True,
    engine: Engine | None = None,
    features: Features = ALL,
) -> list[Relationship]:
    by_lower = {t.name.lower(): t for t in tables}
    by_name = {t.name: t for t in tables}
    single_pk = {t.name: t.pk[0] for t in tables if len(t.pk) == 1}
    rels: dict[tuple[str, str], Relationship] = {}
    skipped: set[tuple[str, str]] = set()  # (table, lowercased column) of skipped keys

    for t in tables:
        for fk in t.fks:
            src_cols = list(fk.get("constrained_columns") or [])
            dst_cols = list(fk.get("referred_columns") or [])
            ref_schema = fk.get("referred_schema")
            if ref_schema is not None and ref_schema != default_schema:
                # Only the default schema is introspected; a same-named table here is a
                # different table, so the key is skipped, never redirected.
                warnings.append(
                    f"skipped foreign key {t.name}.{', '.join(src_cols)}: target "
                    f"{ref_schema}.{fk.get('referred_table')} is outside the introspected schema"
                )
                skipped.update((t.name, c.lower()) for c in src_cols)
                continue
            target_name = _find(
                list(by_name), str(fk.get("referred_table") or ""), case_insensitive
            )
            target = by_name.get(target_name) if target_name else None
            if len(src_cols) != 1 or len(dst_cols) != 1 or target is None:
                warnings.append(f"skipped foreign key on {t.name}: not single-column or unknown")
                skipped.update((t.name, c.lower()) for c in src_cols)
                continue
            dst_col = _find(list(field_slugs[target.name]), dst_cols[0], case_insensitive)
            src_col = _find(list(field_slugs[t.name]), src_cols[0], case_insensitive)
            to_unique = "inferred_links" in features and dst_col in target.unique
            if (
                dst_col is None
                or src_col is None
                or (single_pk.get(target.name) != dst_col and not to_unique)
            ):
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
            if (t.name, col_name) in rels or t.pk == [col_name]:
                continue
            # A declared key that was skipped says where the column points; guessing a
            # different target from its name would invent a wrong join.
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
            if not candidates and "inferred_links" in features and engine is not None:
                candidates = _named_targets(col_name, t, tables, single_pk)
                if len(candidates) == 1 and not _values_contained(
                    engine, t, col_name, by_name[candidates[0]], single_pk[candidates[0]]
                ):
                    warnings.append(
                        f"{t.name}.{col_name}: named like {candidates[0]}, but its values "
                        "are not all its keys; not linked"
                    )
                    continue
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


MIN_DISTINCT_FOR_LINK = 10


def _singular(name: str) -> str:
    lowered = name.lower()
    if lowered.endswith("ies"):
        return lowered[:-3] + "y"
    if lowered.endswith(("ses", "xes", "ches", "shes")):
        return lowered[:-2]
    return lowered.removesuffix("s")


def _named_targets(
    col_name: str, t: _Table, tables: list[_Table], single_pk: dict[str, str]
) -> list[str]:
    """Tables a column is named after, beyond the `<x>_id` forms: the table's name or
    its singular (`airline` -> airlines), or `<role>_<table>_id` with the table's name
    or singular (`origin_airport_id` -> airports). When several tables end the name,
    the longest wins; two of the same length give none."""
    lowered = col_name.lower()
    matches: list[tuple[int, str]] = []
    for target in tables:
        if target.name == t.name or target.name not in single_pk:
            continue
        for form in {target.name.lower(), _singular(target.name)}:
            if lowered == form or (
                lowered.endswith(f"_{form}_id") and len(lowered) > len(form) + 4
            ):
                matches.append((len(form), target.name))
    if not matches:
        return []
    longest = max(length for length, _ in matches)
    return sorted({name for length, name in matches if length == longest})


def _values_contained(
    engine: Engine, t: _Table, col_name: str, target: _Table, target_key: str
) -> bool:
    """Enough evidence that a column holds the target's keys: at least
    MIN_DISTINCT_FOR_LINK distinct values, every one of them a target key. Small integer
    keys contain each other by chance, which is why a name match comes first."""
    src = table(t.name, column(col_name))
    dst = table(target.name, column(target_key))
    value = src.c[col_name]
    with engine.connect() as conn:
        distinct = conn.execute(select(func.count(value.distinct())).select_from(src)).scalar()
        missing = conn.execute(
            select(func.count())
            .select_from(src)
            .where(value.is_not(None), value.not_in(select(dst.c[target_key])))
        ).scalar()
    return int(distinct or 0) >= MIN_DISTINCT_FOR_LINK and int(missing or 0) == 0


_NOT_A_NUMBER_NAME = re.compile(r"(id|code|zip|postal|phone)$", re.IGNORECASE)
_LEADING_ZERO = re.compile(r"^[+-]?0\d")
_NUMBER_SAMPLE = 50
_NUMBER = re.compile(r"^[+-]?(\d+(\.\d*)?|\.\d+)([eE][+-]?\d+)?$")


def _holds_numbers(engine: Engine, t: _Table, col_name: str) -> bool:
    """A text column whose every value, after trimming and skipping placeholders such as
    'null', reads as a number, and that holds at least one. Values with a leading zero
    ('01234') stay text: a zip code or an ID, not an amount."""
    if _NOT_A_NUMBER_NAME.search(col_name):
        return False
    ref = table(t.name, column(col_name))
    col = ref.c[col_name]
    query = select(col).where(col.is_not(None)).distinct()
    try:
        with engine.connect() as conn:
            # Most text columns fail on their first few values, so read a sample before
            # reading them all.
            sample = conn.execute(query.limit(_NUMBER_SAMPLE)).scalars().all()
            if not _all_numbers(sample):
                return False
            if len(sample) < _NUMBER_SAMPLE:
                return any(_reads_as_number(v) for v in sample)
            values = conn.execute(query).scalars().all()
    except OperationalError:
        # SQLite raises when stored bytes are not UTF-8; such a column is not numbers.
        return False
    return _all_numbers(values) and any(_reads_as_number(v) for v in values)


def _reads_as_number(raw: object) -> bool:
    return str(raw).strip() not in TEXT_NUMBER_PLACEHOLDERS


def _all_numbers(values: Sequence[object]) -> bool:
    for raw in values:
        value = str(raw).strip()
        if value in TEXT_NUMBER_PLACEHOLDERS:
            continue
        if _LEADING_ZERO.match(value) or not _NUMBER.match(value):
            return False
    return True


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


def _stored_temporal_type(
    engine: Engine, t: _Table, col_name: str, declared: FieldType
) -> FieldType:
    """SQLite stores whatever it is given, so a DATE column can hold integers such as
    YYYYMMDD. SQLite's date functions read those as day numbers, so a calendar grain
    would turn them into NULL. If every stored value is a number, type the field as one
    (a grain on it is then refused at validation). This reads only each value's storage
    type, never the values themselves."""
    ref = table(t.name, column(col_name))
    kind = func.typeof(ref.c[col_name])
    with engine.connect() as conn:
        kinds = {
            str(row[0])
            for row in conn.execute(
                select(kind).select_from(ref).where(ref.c[col_name].is_not(None)).distinct()
            )
        }
    if not kinds or not kinds <= {"integer", "real"}:
        return declared
    return "integer" if kinds == {"integer"} else "number"


def write_privilege_warning(
    engine: Engine, table_names: list[str], sqlite_path: str | None = None
) -> str | None:
    """A warning when the connecting identity could write. Askwell never writes, but a
    SELECT-only role is the defence that does not depend on Askwell being right."""
    dialect = engine.dialect.name
    if dialect == "sqlite":
        if sqlite_path is not None and os.access(Path(sqlite_path), os.W_OK):
            return "the SQLite file is writable by this user; Askwell opens it read-only"
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


def infer_label(entity: str, primary_key: list[str], fields: dict[str, FieldDef]) -> str | None:
    """The field that names a row, when exactly one visible text field is called `name`,
    `full_name`, `title` or `<entity>_name` (also with the entity's name without a final
    `s`), beside a single-field key. Otherwise none: a wrong guess would group by a key
    where the person meant a value."""
    if len(primary_key) != 1:
        return None
    names = {"name", "full_name", "title", f"{entity}_name", f"{entity.removesuffix('s')}_name"}
    candidates = [
        slug
        for slug, fdef in fields.items()
        if fdef.column.lower() in names
        and fdef.type == "text"
        and not fdef.hidden
        and slug != primary_key[0]
    ]
    return candidates[0] if len(candidates) == 1 else None


def init_registry(
    engine: Engine,
    *,
    include_values: bool = False,
    name: str = "",
    sqlite_path: str | None = None,
    features: Features = ALL,
) -> InitResult:
    tables = _read_tables(engine)
    warnings: list[str] = []
    entity_slug = _unique_slugs([t.name for t in tables])
    field_slugs = {t.name: _unique_slugs([str(c["name"]) for c in t.columns]) for t in tables}
    relationships = _relationships(
        tables,
        entity_slug,
        field_slugs,
        warnings,
        default_schema=inspect(engine).default_schema_name,
        case_insensitive=engine.dialect.name == "sqlite",
        engine=engine,
        features=features,
    )
    key_columns = {(r.from_entity, r.from_field) for r in relationships}

    entities: dict[str, EntityDef] = {}
    for t in tables:
        slug = entity_slug[t.name]
        fields: dict[str, FieldDef] = {}
        for col in t.columns:
            col_name = str(col["name"])
            fslug = field_slugs[t.name][col_name]
            ftype = field_type(col["type"])
            if ftype in TEMPORAL_TYPES and engine.dialect.name == "sqlite":
                ftype = _stored_temporal_type(engine, t, col_name, ftype)
            hidden = bool(SENSITIVE.search(col_name))
            is_key = (
                col_name in t.pk or (slug, fslug) in key_columns or bool(_ID_SUFFIX.match(col_name))
            )
            text_number = (
                "numeric_text" in features
                and ftype == "text"
                and not hidden
                and not is_key
                and _holds_numbers(engine, t, col_name)
            )
            if text_number:
                ftype = "number"
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
                text_number=text_number,
            )
        primary_key = [field_slugs[t.name][c] for c in t.pk if c in field_slugs[t.name]]
        entities[slug] = EntityDef(
            table=t.name,
            kind="view" if t.kind == "view" else "table",
            primary_key=primary_key,
            label=infer_label(slug, primary_key, fields),
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
