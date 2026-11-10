"""Pre-registered Spider question selection, frozen before any intent code exists.

    uv run python -m evals.gold.spider_selection          # write spider_ids.json
    uv run python -m evals.gold.spider_selection --check  # recompute, compare, no write

Rule (fixed here and committed with its output):
1. Source: Spider `dev.json` from the checksum-pinned archive (scripts/fetch_benchmarks.py).
   A question's ID is its 0-based index in dev.json.
2. Eligible databases: dev databases with at least `PER_DB` questions.
3. Five databases are drawn from the eligible ones, sorted by name, with
   `random.Random(SEED).sample`. No database is chosen or excluded by hand or by what
   Ledgerline can express.
4. In each database, questions are stratified by official Spider hardness
   (easy/medium/hard/extra, computed from dev.json's parsed SQL with a port of Spider's
   `eval_hardness`). `PER_DB` slots are allocated proportionally by largest remainder
   (ties go to the earlier hardness level), then sampled within each stratum with the
   same RNG.
Only IDs are committed, never question text or SQL (Spider is CC BY-SA 4.0).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DEV_JSON = ROOT / "data" / "spider" / "spider_data" / "dev.json"
OUT = Path(__file__).resolve().parent / "spider_ids.json"

SEED = 20261109
N_DATABASES = 5
PER_DB = 50
HARDNESS_LEVELS = ("easy", "medium", "hard", "extra")

# --- Port of Spider's hardness (taoyds/spider evaluation.py, Apache-2.0). It is ported
# as is, including its quirks (e.g. `count_agg` over condition units reads the `not`
# flag), because "Spider hardness" means what the official script computes. ---

_WHERE_OPS = ("not", "between", "=", ">", "<", ">=", "<=", "!=", "in", "like", "is", "exists")
_LIKE = _WHERE_OPS.index("like")


def _has_agg(unit: Any) -> bool:
    return unit[0] != 0  # AGG_OPS.index("none") == 0


def _count_agg(units: Any) -> int:
    return len([unit for unit in units if _has_agg(unit)])


def _nested(sql: dict[str, Any]) -> list[Any]:
    nested: list[Any] = []
    for cond in sql["from"]["conds"][::2] + sql["where"][::2] + sql["having"][::2]:
        if isinstance(cond[3], dict):
            nested.append(cond[3])
        if isinstance(cond[4], dict):
            nested.append(cond[4])
    for key in ("intersect", "except", "union"):
        if sql[key] is not None:
            nested.append(sql[key])
    return nested


def _component1(sql: dict[str, Any]) -> int:
    count = 0
    count += len(sql["where"]) > 0
    count += len(sql["groupBy"]) > 0
    count += len(sql["orderBy"]) > 0
    count += sql["limit"] is not None
    if len(sql["from"]["table_units"]) > 0:
        count += len(sql["from"]["table_units"]) - 1
    ao = sql["from"]["conds"][1::2] + sql["where"][1::2] + sql["having"][1::2]
    count += len([op for op in ao if op == "or"])
    conds = sql["from"]["conds"][::2] + sql["where"][::2] + sql["having"][::2]
    count += len([cond for cond in conds if cond[1] == _LIKE])
    return count


def _others(sql: dict[str, Any]) -> int:
    count = 0
    agg = _count_agg(sql["select"][1])
    agg += _count_agg(sql["where"][::2])
    agg += _count_agg(sql["groupBy"])
    if len(sql["orderBy"]) > 0:
        agg += _count_agg(
            [unit[1] for unit in sql["orderBy"][1] if unit[1]]
            + [unit[2] for unit in sql["orderBy"][1] if unit[2]]
        )
    agg += _count_agg(sql["having"])
    count += agg > 1
    count += len(sql["select"][1]) > 1
    count += len(sql["where"]) > 1
    count += len(sql["groupBy"]) > 1
    return count


def spider_hardness(sql: dict[str, Any]) -> str:
    c1, c2, others = _component1(sql), len(_nested(sql)), _others(sql)
    if c1 <= 1 and others == 0 and c2 == 0:
        return "easy"
    if (others <= 2 and c1 <= 1 and c2 == 0) or (c1 <= 2 and others < 2 and c2 == 0):
        return "medium"
    if (
        (others > 2 and c1 <= 2 and c2 == 0)
        or (2 < c1 <= 3 and others <= 2 and c2 == 0)
        or (c1 <= 1 and others == 0 and c2 <= 1)
    ):
        return "hard"
    return "extra"


# --- Selection ---


def allocate(available: dict[str, int], total: int) -> dict[str, int]:
    """Largest-remainder proportional allocation, capped by what each stratum holds."""
    pool = sum(available.values())
    if pool < total:
        raise ValueError(f"only {pool} questions for {total} slots")
    quotas = {level: total * available.get(level, 0) / pool for level in HARDNESS_LEVELS}
    alloc = {level: int(quotas[level]) for level in HARDNESS_LEVELS}
    order = sorted(
        HARDNESS_LEVELS,
        key=lambda level: (-(quotas[level] - alloc[level]), HARDNESS_LEVELS.index(level)),
    )
    for level in order[: total - sum(alloc.values())]:
        alloc[level] += 1
    return {level: alloc[level] for level in HARDNESS_LEVELS if available.get(level, 0)}


def select(dev: list[dict[str, Any]], seed: int = SEED) -> dict[str, Any]:
    rng = random.Random(seed)
    by_db: dict[str, list[int]] = {}
    for index, example in enumerate(dev):
        by_db.setdefault(example["db_id"], []).append(index)
    eligible = sorted(db for db, ids in by_db.items() if len(ids) >= PER_DB)
    if len(eligible) < N_DATABASES:
        raise ValueError(f"only {len(eligible)} databases have >= {PER_DB} questions")
    chosen = rng.sample(eligible, N_DATABASES)

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
        "eligible_databases": eligible,
        "databases": databases,
    }


def build(dev_json: Path) -> dict[str, Any]:
    raw = dev_json.read_bytes()
    dev = json.loads(raw)
    result = select(dev)
    hardness = Counter(spider_hardness(example["sql"]) for example in dev)
    return {
        "source": {
            "file": "spider_data/dev.json",
            "dev_json_sha256": hashlib.sha256(raw).hexdigest(),
            "dev_questions": len(dev),
            "dev_hardness": {level: hardness[level] for level in HARDNESS_LEVELS},
        },
        "rule": "see evals/gold/spider_selection.py docstring",
        **result,
    }


def render(selection: dict[str, Any]) -> str:
    return json.dumps(selection, indent=2) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Pre-registered Spider ID selection.")
    parser.add_argument("--dev-json", type=Path, default=DEV_JSON)
    parser.add_argument("--check", action="store_true", help="compare with the committed file")
    args = parser.parse_args(argv)
    if not args.dev_json.exists():
        print(f"{args.dev_json} not found: run `uv run python -m scripts.fetch_benchmarks`")
        return 1
    text = render(build(args.dev_json))
    if args.check:
        if OUT.read_text() != text:
            print("spider_ids.json does NOT match a fresh selection", file=sys.stderr)
            return 1
        print("spider_ids.json matches a fresh selection")
        return 0
    OUT.write_text(text)
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
