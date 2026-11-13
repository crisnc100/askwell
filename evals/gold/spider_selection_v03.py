"""Untriaged Spider questions for v0.3, selected before any v0.3 code.

    uv run python -m evals.gold.spider_selection_v03          # write spider_ids_v03.json
    uv run python -m evals.gold.spider_selection_v03 --check  # recompute, compare, no write

Rule (fixed here and committed with its output):
1. Source: the same checksum-pinned Spider `dev.json` as `spider_selection.py`.
2. Databases: every dev database with at least `PER_DB` questions that
   `spider_ids.json` does not already use. All of them are taken, so none is chosen by
   draw or by hand. The rule expects exactly `N_DATABASES` and refuses otherwise.
3. In each database, questions are stratified by Spider hardness and sampled exactly as
   `spider_selection.py` does (its `allocate` and `spider_hardness`), with this file's
   `SEED`, in database-name order.
`spider_selection.py` stays unchanged: it is frozen and draws its own five databases.
Only IDs are committed, never question text or SQL (Spider is CC BY-SA 4.0).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
from pathlib import Path
from typing import Any

from evals.gold.spider_selection import (
    DEV_JSON,
    HARDNESS_LEVELS,
    PER_DB,
    allocate,
    spider_hardness,
)

GOLD_DIR = Path(__file__).resolve().parent
USED = GOLD_DIR / "spider_ids.json"
OUT = GOLD_DIR / "spider_ids_v03.json"

SEED = 20261113
N_DATABASES = 4


def used_databases(used: dict[str, Any]) -> set[str]:
    return {db["db_id"] for db in used["databases"]}


def select(dev: list[dict[str, Any]], used: set[str], seed: int = SEED) -> dict[str, Any]:
    rng = random.Random(seed)
    by_db: dict[str, list[int]] = {}
    for index, example in enumerate(dev):
        by_db.setdefault(example["db_id"], []).append(index)
    eligible = sorted(db for db, ids in by_db.items() if len(ids) >= PER_DB)
    chosen = [db for db in eligible if db not in used]
    if len(chosen) != N_DATABASES:
        raise ValueError(f"expected {N_DATABASES} unused databases, found {len(chosen)}")

    databases: list[dict[str, Any]] = []
    for db in chosen:
        strata: dict[str, list[int]] = {level: [] for level in HARDNESS_LEVELS}
        for index in by_db[db]:
            strata[spider_hardness(dev[index]["sql"])].append(index)
        available = {level: len(ids) for level, ids in strata.items() if ids}
        alloc = allocate(available, PER_DB)
        picked: list[int] = []
        for level in HARDNESS_LEVELS:
            if alloc.get(level):
                picked.extend(rng.sample(strata[level], alloc[level]))
        databases.append(
            {
                "db_id": db,
                "dev_questions": len(by_db[db]),
                "hardness_available": available,
                "hardness_selected": alloc,
                "ids": sorted(picked),
            }
        )
    return {
        "seed": seed,
        "per_db": PER_DB,
        "n_databases": N_DATABASES,
        "excluded_as_used": sorted(used),
        "databases": databases,
    }


def build(dev_json: Path, used_file: Path = USED) -> dict[str, Any]:
    raw = dev_json.read_bytes()
    used = used_databases(json.loads(used_file.read_text()))
    return {
        "source": {
            "file": "spider_data/dev.json",
            "dev_json_sha256": hashlib.sha256(raw).hexdigest(),
        },
        "rule": "see evals/gold/spider_selection_v03.py docstring",
        **select(json.loads(raw), used),
    }


def render(selection: dict[str, Any]) -> str:
    return json.dumps(selection, indent=2) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Untriaged Spider ID selection for v0.3.")
    parser.add_argument("--dev-json", type=Path, default=DEV_JSON)
    parser.add_argument("--check", action="store_true", help="compare with the committed file")
    args = parser.parse_args(argv)
    if not args.dev_json.exists():
        print(f"{args.dev_json} not found: run `uv run python -m scripts.fetch_benchmarks`")
        return 1
    text = render(build(args.dev_json))
    if args.check:
        if OUT.read_text() != text:
            print("spider_ids_v03.json does NOT match a fresh selection", file=sys.stderr)
            return 1
        print("spider_ids_v03.json matches a fresh selection")
        return 0
    OUT.write_text(text)
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
