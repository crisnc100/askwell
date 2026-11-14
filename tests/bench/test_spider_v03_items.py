"""The untriaged Spider databases (evals/gold/spider_ids_v03.json) run like the triaged
ones, but their records name their own ID file as the gold, so reports keep the two sets
apart. `--all` stays the triaged set. Synthetic files only: the untriaged databases and
their questions are not read here."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from askwell.bench import items, spider


def _ids_file(path: Path, db_ids: dict[str, list[int]]) -> Path:
    path.write_text(
        json.dumps({"databases": [{"db_id": db, "ids": ids} for db, ids in db_ids.items()]})
    )
    return path


@pytest.fixture
def two_sets(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    old = _ids_file(tmp_path / "spider_ids.json", {"alpha": [0]})
    new = _ids_file(tmp_path / "spider_ids_v03.json", {"beta": [1, 2]})
    monkeypatch.setattr(items, "SPIDER_IDS", old)
    monkeypatch.setattr(items, "SPIDER_ID_FILES", (old, new))
    data = tmp_path / "spider_data"
    data.mkdir()
    dev: list[dict[str, Any]] = [
        {"db_id": db, "question": f"q{n}", "query": "SELECT 1", "sql": {}}
        for n, db in enumerate(["alpha", "beta", "beta"])
    ]
    (data / "dev.json").write_text(json.dumps(dev))
    monkeypatch.setattr(items, "SPIDER_DIR", data)
    from evals.gold import spider_selection

    monkeypatch.setattr(spider_selection, "spider_hardness", lambda _sql: "easy")


@pytest.mark.usefixtures("two_sets")
def test_an_untriaged_database_reads_its_own_id_file() -> None:
    got = items.spider_items("beta")
    assert [i.id for i in got] == ["spider:1", "spider:2"]
    assert {i.gold for i in got} == {"spider_ids_v03.json"}
    assert {i.schema_id for i in got} == {"spider_beta"}
    assert items.default_gold("spider_beta") == "spider_ids_v03.json"


@pytest.mark.usefixtures("two_sets")
def test_the_triaged_set_is_unchanged() -> None:
    [item] = items.spider_items("alpha")
    assert item.gold == "spider_ids.json"
    assert items.default_gold("spider_alpha") == "spider_ids.json"
    assert items.spider_databases() == ["alpha"]


@pytest.mark.usefixtures("two_sets")
def test_a_database_in_neither_file_is_refused() -> None:
    with pytest.raises(ValueError, match="pre-registered"):
        items.spider_items("gamma")


def test_the_real_files_do_not_share_a_database() -> None:
    sets = [
        {db["db_id"] for db in json.loads(path.read_text())["databases"]}
        for path in items.SPIDER_ID_FILES
    ]
    assert len(sets) == 2
    assert not sets[0] & sets[1]


def test_writing_hashes_keeps_the_others(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    hashes = tmp_path / "spider_registries.json"
    hashes.write_text(json.dumps({"car_1": "a" * 64}))
    monkeypatch.setattr(spider, "HASHES", hashes)
    monkeypatch.setattr(spider, "generate", lambda db_id: f"registry {db_id}")
    written = spider.write_hashes(["tvshow"])
    assert written == {"tvshow": spider.sha256("registry tvshow")}
    assert json.loads(hashes.read_text()) == {
        "car_1": "a" * 64,
        "tvshow": spider.sha256("registry tvshow"),
    }
