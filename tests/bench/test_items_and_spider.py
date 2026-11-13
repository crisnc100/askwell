"""Eval items and the Spider registry-hash check."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from askwell.bench import spider
from askwell.bench.items import fieldservice_items, spider_databases, spider_items


def test_fieldservice_items_are_the_gold_set() -> None:
    items = fieldservice_items()
    assert len(items) == 67
    assert {i.schema_id for i in items} == {"fieldservice"}


@pytest.mark.parametrize("db_id", spider_databases())
def test_spider_items_follow_the_preregistered_ids(db_id: str) -> None:
    items = spider_items(db_id)
    committed = json.loads(Path("evals/gold/spider_ids.json").read_text())
    ids = next(db["ids"] for db in committed["databases"] if db["db_id"] == db_id)
    assert [i.id for i in items] == [f"spider:{n}" for n in ids]
    assert {i.category for i in items} == {"in_schema"}
    assert all(i.gold_sql for i in items)


@pytest.mark.parametrize("db_id", spider_databases())
def test_regenerated_spider_registries_match_committed_hashes(db_id: str) -> None:
    config, digest = spider.schema_for(db_id)
    assert digest == spider.committed_hashes()[db_id]
    assert config.allow_draft


def test_registry_drift_stops_the_eval(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(spider, "committed_hashes", lambda: {"car_1": "0" * 64})
    with pytest.raises(spider.RegistryDriftError, match="car_1"):
        spider.schema_for("car_1")
    monkeypatch.setattr(spider, "committed_hashes", lambda: {})
    with pytest.raises(spider.RegistryDriftError, match="no committed"):
        spider.schema_for("car_1")


def test_unknown_spider_db_is_refused() -> None:
    with pytest.raises(ValueError, match="pre-registered"):
        spider_items("academic")
