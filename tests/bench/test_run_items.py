"""A run on named items only (`--items`), for a targeted gate such as v03-roles-seen:
only those items are asked, every schema runs the trials asked for, and a named item
that no schema has stops the run before any model call."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from askwell.bench import run as run_module
from askwell.bench.items import spider_items
from askwell.config import get_settings

ROLES_SEEN = Path(__file__).resolve().parents[2] / "evals" / "v03_roles_seen.json"


@pytest.fixture
def isolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(run_module, "RUNS_DIR", tmp_path / "runs")
    monkeypatch.setattr(run_module, "EVAL_RECORDINGS", tmp_path / "recordings")
    monkeypatch.setattr(run_module, "EVAL_PENDING", tmp_path / "pending")
    return tmp_path


def test_only_named_items_run_with_every_trial(isolated: Path) -> None:
    result = run_module.run_eval(
        get_settings(),
        run_id="t",
        schema_ids=["spider_network_1"],
        systems=["ledgerline"],
        mode="export",
        models=["target/model"],
        trials=3,
        budget_usd=1.0,
        item_ids={"spider:885", "spider:886"},
    )
    assert result.deferred == {"spider_network_1/ledgerline": 6}


def test_a_named_item_no_schema_has_stops_the_run(isolated: Path) -> None:
    with pytest.raises(ValueError, match="spider:1"):
        run_module.run_eval(
            get_settings(),
            run_id="t",
            schema_ids=["spider_network_1"],
            systems=["ledgerline"],
            mode="export",
            models=["target/model"],
            trials=1,
            budget_usd=1.0,
            item_ids={"spider:885", "spider:1"},
        )
    assert not (isolated / "pending").exists()


def test_the_roles_gate_items_are_the_26_two_link_refusals() -> None:
    ids = json.loads(ROLES_SEEN.read_text())["ids"]
    assert len(ids) == len(set(ids)) == 26
    seen = {item.id for db in ("network_1", "wta_1") for item in spider_items(db)}
    assert set(ids) <= seen
