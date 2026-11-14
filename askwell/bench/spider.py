"""Spider registries: made by `registry init --values` at eval time, never edited.

Only each registry's SHA-256 is committed (`evals/spider_registries.json`): the YAML
itself holds Spider data (allowed values), which is CC BY-SA. The eval stops if a
freshly generated registry does not match its committed hash.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from askwell.bench.items import ROOT, SPIDER_DIR
from askwell.core.executor import readonly_engine
from askwell.core.features import ALL, Features
from askwell.core.registry import dump_registry
from askwell.core.registry_init import init_registry
from askwell.pipeline.service import SchemaConfig

HASHES = ROOT / "evals" / "spider_registries.json"
REGISTRY_DIR = ROOT / "data" / "registries"


class RegistryDriftError(RuntimeError):
    """A regenerated Spider registry differs from its committed hash."""


def db_path(db_id: str) -> Path:
    return SPIDER_DIR / "database" / db_id / f"{db_id}.sqlite"


def generate(db_id: str, features: Features = ALL) -> str:
    path = db_path(db_id)
    if not path.exists():
        raise FileNotFoundError(f"{path}: run `uv run python -m scripts.fetch_benchmarks`")
    engine = readonly_engine(f"sqlite:///{path}")
    try:
        return dump_registry(
            init_registry(engine, include_values=True, name=db_id, features=features).registry
        )
    finally:
        engine.dispose()


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def committed_hashes() -> dict[str, str]:
    return json.loads(HASHES.read_text()) if HASHES.exists() else {}


def schema_for(
    db_id: str, *, check: bool = True, features: Features = ALL
) -> tuple[SchemaConfig, str]:
    """Generate the registry, check it against the committed hash, write it to the
    gitignored data/registries/, and return the schema config and the hash.

    The committed hashes are for every feature on; a run with a feature off draws a
    different registry, so its hash is recorded but not checked."""
    text = generate(db_id, features)
    digest = sha256(text)
    if check and features == ALL:
        expected = committed_hashes().get(db_id)
        if expected is None:
            raise RegistryDriftError(f"{db_id}: no committed registry hash in {HASHES.name}")
        if expected != digest:
            raise RegistryDriftError(
                f"{db_id}: regenerated registry {digest[:12]} != committed {expected[:12]}"
            )
    REGISTRY_DIR.mkdir(parents=True, exist_ok=True)
    path = REGISTRY_DIR / f"{db_id}.yaml"
    path.write_text(text, encoding="utf-8")
    schema = SchemaConfig(
        id=f"spider_{db_id}",
        title=db_id,
        registry_path=path,
        db_url=f"sqlite:///{db_path(db_id)}",
        allow_draft=True,
    )
    return schema, digest


def write_hashes(db_ids: list[str]) -> dict[str, str]:
    hashes = {db_id: sha256(generate(db_id)) for db_id in db_ids}
    HASHES.write_text(json.dumps(hashes, indent=2, sort_keys=True) + "\n")
    return hashes
