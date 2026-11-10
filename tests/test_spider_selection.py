"""Spider pre-registration: the hardness port, allocation, seeded selection and the
committed ID file (IDs only, never question text)."""

from __future__ import annotations

import json
from collections import Counter
from typing import Any

import pytest

from evals.gold.spider_selection import (
    HARDNESS_LEVELS,
    N_DATABASES,
    OUT,
    PER_DB,
    SEED,
    allocate,
    select,
    spider_hardness,
)

COL = [0, [0, [0, 1, False], None]]  # a val_unit-bearing select item, no aggregation
AGG = [3, [0, [0, 1, False], None]]  # count(...)
COND = [False, 2, [0, [0, 1, False], None], 1.0, None]  # col = value
LIKE = [False, 9, [0, [0, 1, False], None], '"%a%"', None]


def sql(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "select": [False, [COL]],
        "from": {"table_units": [["table_unit", 0]], "conds": []},
        "where": [],
        "groupBy": [],
        "having": [],
        "orderBy": [],
        "limit": None,
        "intersect": None,
        "union": None,
        "except": None,
    }
    base.update(overrides)
    return base


def test_hardness_easy() -> None:
    assert spider_hardness(sql()) == "easy"
    assert spider_hardness(sql(where=[COND])) == "easy"


def test_hardness_medium() -> None:
    assert spider_hardness(sql(where=[COND], limit=1)) == "medium"
    assert spider_hardness(sql(select=[False, [COL, AGG]])) == "medium"


def test_hardness_hard() -> None:
    joined = {"table_units": [["table_unit", 0], ["table_unit", 1]], "conds": []}
    assert spider_hardness(sql(**{"from": joined}, where=[COND], groupBy=[[0, 1, False]])) == (
        "hard"
    )
    assert spider_hardness(sql(intersect=sql())) == "hard"


def test_hardness_extra() -> None:
    assert spider_hardness(sql(where=[COND, "or", LIKE], limit=1, union=sql())) == "extra"


def test_allocate_is_proportional_and_exact() -> None:
    alloc = allocate({"easy": 10, "medium": 36, "hard": 10, "extra": 26}, 50)
    assert sum(alloc.values()) == 50
    assert alloc == {"easy": 6, "medium": 22, "hard": 6, "extra": 16}


def test_allocate_ties_go_to_earlier_level() -> None:
    assert allocate({"easy": 1, "medium": 1, "hard": 1, "extra": 1}, 2) == {
        "easy": 1,
        "medium": 1,
        "hard": 0,
        "extra": 0,
    }


def test_allocate_refuses_too_few_questions() -> None:
    with pytest.raises(ValueError, match="only 3"):
        allocate({"easy": 3}, 50)


def _synthetic_dev() -> list[dict[str, Any]]:
    shapes = [sql(), sql(where=[COND], limit=1), sql(intersect=sql()), sql(union=sql(), limit=1)]
    dev: list[dict[str, Any]] = []
    for db_number in range(8):
        size = 40 if db_number == 0 else 60 + db_number
        for i in range(size):
            dev.append({"db_id": f"db_{db_number}", "sql": shapes[(i * 7 + db_number) % 4]})
    return dev


def test_selection_is_deterministic_and_stratified() -> None:
    dev = _synthetic_dev()
    first, second = select(dev), select(dev)
    assert first == second
    assert first["seed"] == SEED
    assert "db_0" not in first["eligible_databases"]  # under PER_DB questions
    assert len(first["databases"]) == N_DATABASES
    for db in first["databases"]:
        assert len(db["ids"]) == PER_DB == len(set(db["ids"]))
        assert all(dev[i]["db_id"] == db["db_id"] for i in db["ids"])
        got = Counter(spider_hardness(dev[i]["sql"]) for i in db["ids"])
        assert dict(got) == {k: v for k, v in db["hardness_selected"].items() if v}


def test_a_different_seed_changes_the_selection() -> None:
    dev = _synthetic_dev()
    assert select(dev, seed=1) != select(dev)


def test_committed_ids_file_holds_ids_only() -> None:
    committed = json.loads(OUT.read_text())
    assert set(committed) == {
        "source",
        "rule",
        "seed",
        "per_db",
        "n_databases",
        "eligible_databases",
        "databases",
    }
    assert set(committed["source"]) == {"file", "dev_json_sha256", "dev_questions", "dev_hardness"}
    assert committed["seed"] == SEED
    assert len(committed["databases"]) == N_DATABASES
    for db in committed["databases"]:
        assert set(db) == {
            "db_id",
            "dev_questions",
            "hardness_available",
            "hardness_selected",
            "ids",
        }
        assert db["db_id"] in committed["eligible_databases"]
        assert len(db["ids"]) == PER_DB == len(set(db["ids"]))
        assert all(
            isinstance(i, int) and 0 <= i < committed["source"]["dev_questions"] for i in db["ids"]
        )
        assert sum(db["hardness_selected"].values()) == PER_DB
        assert set(db["hardness_selected"]) <= set(HARDNESS_LEVELS)


def test_committed_hardness_totals_match_published_spider_dev() -> None:
    """Spider's dev split is published as 248 easy / 446 medium / 174 hard / 166 extra;
    matching it validates the hardness port on the real data."""
    committed = json.loads(OUT.read_text())
    assert committed["source"]["dev_hardness"] == {
        "easy": 248,
        "medium": 446,
        "hard": 174,
        "extra": 166,
    }
