"""`registry init`: deterministic, auto-hides sensitive fields, infers relationships, and
its output loads, on fieldservice (both engines) and every sampled Spider DB."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from sqlalchemy import Engine, create_engine, text

from ledgerline.core.executor import readonly_engine
from ledgerline.core.registry import Registry, dump_registry, load_registry
from ledgerline.core.registry_init import field_type, init_registry, write_privilege_warning
from tests.core.conftest import FIELDSERVICE_REGISTRY, ROOT

SPIDER_DB_DIR = ROOT / "data" / "spider" / "spider_data" / "database"
SPIDER_IDS = json.loads((ROOT / "evals" / "gold" / "spider_ids.json").read_text())
SPIDER_DBS = [db["db_id"] for db in SPIDER_IDS["databases"]]


def _init_twice(engine: Engine, **kw: object) -> tuple[str, str]:
    first = dump_registry(init_registry(engine, **kw).registry)  # type: ignore[arg-type]
    second = dump_registry(init_registry(engine, **kw).registry)  # type: ignore[arg-type]
    return first, second


@pytest.mark.parametrize("engine_name", ["postgresql", "sqlite"])
def test_fieldservice_init_is_deterministic_and_hides(
    engine_name: str, pg_seeded: Engine, sqlite_ro: Engine, tmp_path: Path
) -> None:
    engine = pg_seeded if engine_name == "postgresql" else sqlite_ro
    first, second = _init_twice(engine, include_values=True, name="fieldservice")
    assert first == second
    path = tmp_path / "fs.yaml"
    path.write_text(first)
    registry = load_registry(path)
    assert registry.draft
    users = registry.entities["users"].fields
    assert users["email"].hidden
    assert users["password_hash"].hidden
    assert not users["email"].filterable
    assert not users["username"].hidden
    assert registry.entities["work_orders"].fields["status"].allowed_values == [
        "cancelled",
        "completed",
        "in_progress",
        "open",
        "scheduled",
    ]
    # Names and one-value-per-row text never become categorical.
    assert not registry.entities["customers"].fields["name"].categorical
    assert not registry.entities["parts"].fields["sku"].categorical
    assert len(registry.relationships) == 6
    assert {r.source for r in registry.relationships} == {"declared"}


def test_both_engines_give_the_same_registry(pg_seeded: Engine, sqlite_ro: Engine) -> None:
    pg = init_registry(pg_seeded, include_values=True).registry
    lite = init_registry(sqlite_ro, include_values=True).registry
    assert pg == lite


def test_without_values_no_data_is_read(sqlite_ro: Engine) -> None:
    registry = init_registry(sqlite_ro).registry
    assert not any(
        f.categorical or f.allowed_values
        for e in registry.entities.values()
        for f in e.fields.values()
    )


def test_curated_fieldservice_registry_matches_introspection(sqlite_ro: Engine) -> None:
    """Curation may only add descriptions, aliases, value aliases and clear `draft`."""
    fresh = init_registry(sqlite_ro, include_values=True, name="fieldservice").registry
    curated = load_registry(FIELDSERVICE_REGISTRY)
    assert curated.relationships == fresh.relationships
    assert list(curated.entities) == list(fresh.entities)
    for slug, entity in fresh.entities.items():
        other = curated.entities[slug]
        assert (other.table, other.kind, other.primary_key) == (
            entity.table,
            entity.kind,
            entity.primary_key,
        )
        assert list(other.fields) == list(entity.fields)
        for fslug, fdef in entity.fields.items():
            got = other.fields[fslug]
            keep = (
                "column",
                "type",
                "filterable",
                "aggregatable",
                "hidden",
                "categorical",
                "allowed_values",
            )
            assert {k: getattr(got, k) for k in keep} == {k: getattr(fdef, k) for k in keep}


def test_write_privileges_are_reported(pg_owner: Engine, pg_seeded: Engine) -> None:
    tables = ["parts", "invoices"]
    owner_warning = write_privilege_warning(pg_owner, tables)
    assert owner_warning is not None
    assert "can write" in owner_warning
    assert write_privilege_warning(pg_seeded, tables) is None
    assert init_registry(pg_seeded).warnings == []


def test_sqlite_write_warning(tmp_path: Path, sqlite_ro: Engine) -> None:
    path = tmp_path / "w.sqlite"
    path.write_bytes(b"")
    assert write_privilege_warning(sqlite_ro, [], str(path)) is not None
    os.chmod(path, 0o444)
    try:
        assert write_privilege_warning(sqlite_ro, [], str(path)) is None
    finally:
        os.chmod(path, 0o644)
    assert write_privilege_warning(sqlite_ro, []) is None
    mysql_like = create_engine("sqlite://")
    mysql_like.dialect.name = "mysql"
    assert write_privilege_warning(mysql_like, []) == "cannot check write privileges on mysql"


def _sqlite(tmp_path: Path, ddl: list[str]) -> Engine:
    path = tmp_path / "db.sqlite"
    writer = create_engine(f"sqlite:///{path}")
    with writer.begin() as conn:
        for statement in ddl:
            conn.execute(text(statement))
    writer.dispose()
    return readonly_engine(f"sqlite:///{path}")


def test_relationships_are_inferred_without_foreign_keys(tmp_path: Path) -> None:
    engine = _sqlite(
        tmp_path,
        [
            "CREATE TABLE owners (id INTEGER PRIMARY KEY, name TEXT)",
            "CREATE TABLE dogs (dog_id INTEGER PRIMARY KEY, owner_id INTEGER, breed_code TEXT)",
            "CREATE TABLE breeds (breed_code TEXT PRIMARY KEY, label TEXT)",
            "CREATE TABLE treatments (id INTEGER PRIMARY KEY, dog_id INTEGER, cost REAL)",
            "CREATE TABLE notes (id INTEGER PRIMARY KEY, nothing_id INTEGER)",
        ],
    )
    registry = init_registry(engine).registry
    rels = {
        (r.from_entity, r.from_field, r.to_entity, r.to_field, r.source)
        for r in registry.relationships
    }
    assert rels == {
        ("dogs", "owner_id", "owners", "id", "inferred"),  # owner_id -> owners
        ("dogs", "breed_code", "breeds", "breed_code", "inferred"),  # same name as a PK
        ("treatments", "dog_id", "dogs", "dog_id", "inferred"),  # dog_id -> dogs
    }
    # Key columns are not aggregatable; measures are.
    assert not registry.entities["treatments"].fields["dog_id"].aggregatable
    assert registry.entities["treatments"].fields["cost"].aggregatable


def test_declared_foreign_keys_win_and_bad_ones_are_skipped(tmp_path: Path) -> None:
    engine = _sqlite(
        tmp_path,
        [
            "CREATE TABLE a (id INTEGER PRIMARY KEY, code TEXT, x INTEGER, y INTEGER)",
            "CREATE TABLE b (id INTEGER PRIMARY KEY, a_ref INTEGER REFERENCES a(id), "
            "a_code TEXT REFERENCES a(code), ghost INTEGER REFERENCES missing(id))",
            "CREATE TABLE c (id INTEGER PRIMARY KEY, x INTEGER, y INTEGER, "
            "FOREIGN KEY (x, y) REFERENCES a(x, y))",
        ],
    )
    result = init_registry(engine)
    rels = {
        (r.from_entity, r.from_field, r.to_entity, r.source) for r in result.registry.relationships
    }
    assert rels == {("b", "a_ref", "a", "declared")}
    assert any("not a primary key" in w for w in result.warnings)
    assert any("not single-column or unknown" in w for w in result.warnings)


def test_ambiguous_inference_keeps_nothing(tmp_path: Path) -> None:
    engine = _sqlite(
        tmp_path,
        [
            "CREATE TABLE item (id INTEGER PRIMARY KEY)",
            "CREATE TABLE items (id INTEGER PRIMARY KEY)",
            "CREATE TABLE orders (id INTEGER PRIMARY KEY, item_id INTEGER)",
        ],
    )
    result = init_registry(engine)
    assert result.registry.relationships == []
    assert any("several inferred targets" in w for w in result.warnings)


def test_odd_names_get_safe_unique_slugs_and_views_load(tmp_path: Path) -> None:
    engine = _sqlite(
        tmp_path,
        [
            'CREATE TABLE "Order Lines" ("Line ID" INTEGER PRIMARY KEY, "line-id" INTEGER, '
            '"Unit.Price" NUMERIC, "Secret Token" TEXT, "Phone" TEXT, "Kind" TEXT, '
            '"Created" DATETIME, "Shipped" DATE, "Ok" BOOLEAN, "Blob" BLOB)',
            'CREATE TABLE "order_lines" (id INTEGER PRIMARY KEY)',
            'CREATE VIEW "Big Lines" AS SELECT * FROM "Order Lines" WHERE "Unit.Price" > 10',
        ]
        + [
            f"INSERT INTO \"Order Lines\" VALUES ({i}, {i}, {i}.5, 't', 'p', "
            f"'{'ab'[i % 2]}', '2026-01-01 00:00:00', '2026-01-01', 1, NULL)"
            for i in range(1, 9)
        ],
    )
    registry = init_registry(engine, include_values=True).registry
    assert list(registry.entities) == ["big_lines", "order_lines", "order_lines_2"]
    lines = registry.entities["order_lines"]
    assert lines.table == "Order Lines"
    assert list(lines.fields) == [
        "line_id",
        "line_id_2",
        "unit_price",
        "secret_token",
        "phone",
        "kind",
        "created",
        "shipped",
        "ok",
        "blob",
    ]
    types = {k: f.type for k, f in lines.fields.items()}
    assert types["unit_price"] == "number"
    assert types["created"] == "datetime"
    assert types["shipped"] == "date"
    assert types["ok"] == "boolean"
    assert types["blob"] == "text"
    assert lines.fields["secret_token"].hidden
    assert lines.fields["phone"].hidden
    assert lines.fields["kind"].allowed_values == ["a", "b"]
    assert registry.entities["big_lines"].kind == "view"
    assert Registry.model_validate(registry.model_dump()) == registry


def test_field_type_falls_back_to_text() -> None:
    assert field_type(object()) == "text"


@pytest.mark.parametrize("db_id", SPIDER_DBS)
def test_every_sampled_spider_db(db_id: str, tmp_path: Path) -> None:
    path = SPIDER_DB_DIR / db_id / f"{db_id}.sqlite"
    if not path.exists():
        pytest.fail(
            f"{path} missing: run `uv run python -m scripts.fetch_benchmarks` (tests never skip)"
        )
    engine = readonly_engine(f"sqlite:///{path}")
    try:
        first, second = _init_twice(engine, include_values=True, name=db_id)
    finally:
        engine.dispose()
    assert first == second
    out = tmp_path / f"{db_id}.yaml"
    out.write_text(first)
    registry = load_registry(out)
    assert registry.draft
    assert registry.entities
    assert all(f.column for e in registry.entities.values() for f in e.fields.values())


def test_date_columns_holding_integers_are_typed_integer(tmp_path: Path) -> None:
    """A DATE column storing YYYYMMDD integers is not a date to SQLite's date functions;
    typed as integer, a calendar grain on it is refused at validation (grain_type)."""
    from ledgerline.core.intent import Intent
    from ledgerline.core.validate import validate
    from tests.core.conftest import NOW

    engine = _sqlite(
        tmp_path,
        [
            "CREATE TABLE r (id INTEGER PRIMARY KEY, day DATE, real_day DATE)",
            "INSERT INTO r VALUES (1, 20010203, '2001-02-03'), (2, 20010204, '2001-02-04')",
        ],
    )
    registry = init_registry(engine).registry
    fields = registry.entities["r"].fields
    assert fields["day"].type == "integer"
    assert fields["real_day"].type == "date"
    intent = Intent.model_validate(
        {
            "intent_type": "grouped_summary",
            "entity": "r",
            "metrics": [{"agg": "count"}],
            "group_by": [{"field": "day", "grain": "month"}],
        }
    )
    result = validate(intent, registry, now=NOW, allow_draft=True)
    assert result.codes == ["grain_type"]
