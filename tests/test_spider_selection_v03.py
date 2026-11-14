"""v0.3's untriaged Spider selection, on a synthetic dev set (no Spider data needed)."""

from __future__ import annotations

from typing import Any

import pytest

from evals.gold.spider_selection import PER_DB, spider_hardness
from evals.gold.spider_selection_v03 import N_DATABASES, SEED, select

EMPTY_FROM = {"table_units": [["table_unit", 0]], "conds": []}
COL = [0, [0, [0, 1, False], None]]
COND = [False, 2, [0, [0, 1, False], None], 1.0, None]


def sql(where: int) -> dict[str, Any]:
    return {
        "select": [False, [COL]],
        "from": EMPTY_FROM,
        "where": [COND] if where else [],
        "groupBy": [],
        "having": [],
        "orderBy": [],
        "limit": 1 if where > 1 else None,
        "intersect": None,
        "union": None,
        "except": None,
    }


def dev_set(sizes: dict[str, int]) -> list[dict[str, Any]]:
    return [
        {"db_id": db, "sql": sql(i % 3)} for db, size in sorted(sizes.items()) for i in range(size)
    ]


SIZES = {
    "used_a": 60,
    "used_b": 55,
    "new_a": 70,
    "new_b": 50,
    "new_c": 64,
    "new_d": 90,
    "small": PER_DB - 1,
}


def test_takes_every_unused_database_with_enough_questions() -> None:
    result = select(dev_set(SIZES), {"used_a", "used_b"})
    assert [db["db_id"] for db in result["databases"]] == ["new_a", "new_b", "new_c", "new_d"]
    assert result["excluded_as_used"] == ["used_a", "used_b"]
    assert result["seed"] == SEED
    assert result["n_databases"] == N_DATABASES


def test_each_database_gets_per_db_distinct_ids_from_itself_stratified() -> None:
    dev = dev_set(SIZES)
    for db in select(dev, {"used_a", "used_b"})["databases"]:
        ids = db["ids"]
        assert len(ids) == len(set(ids)) == PER_DB
        assert all(dev[i]["db_id"] == db["db_id"] for i in ids)
        picked: dict[str, int] = {}
        for i in ids:
            level = spider_hardness(dev[i]["sql"])
            picked[level] = picked.get(level, 0) + 1
        assert picked == db["hardness_selected"]


def test_the_same_seed_gives_the_same_ids() -> None:
    dev = dev_set(SIZES)
    assert select(dev, {"used_a", "used_b"}) == select(dev, {"used_a", "used_b"})
    assert select(dev, {"used_a", "used_b"}, seed=1) != select(dev, {"used_a", "used_b"})


def test_refuses_when_the_unused_count_is_not_as_expected() -> None:
    with pytest.raises(ValueError, match="expected 4 unused databases, found 5"):
        select(dev_set(SIZES), {"used_a"})
