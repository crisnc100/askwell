"""`askwell eval --gold <file>`: a second gold file for the same schema. The report
names the gold file in its header and in every row, so seen and held-out results are
never mixed up."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy import Engine
from typer.testing import CliRunner

from askwell.bench import report as report_module
from askwell.bench import run as run_module
from askwell.bench.report_schema import Report
from askwell.cli import app
from askwell.config import get_settings
from askwell.llm.replay import ReplayStore
from askwell.llm.simulate import answer_path, import_answers, pending_requests

FIXTURE = Path(__file__).parent / "fixtures" / "gold-two.jsonl"


@pytest.fixture
def isolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(run_module, "RUNS_DIR", tmp_path / "runs")
    monkeypatch.setattr(run_module, "EVAL_RECORDINGS", tmp_path / "recordings")
    monkeypatch.setattr(run_module, "EVAL_PENDING", tmp_path / "pending")
    monkeypatch.setattr(report_module, "TRIAGE_DIR", tmp_path / "triage")
    return tmp_path


def _run(mode: str, gold: Path | None) -> run_module.RunResult:
    return run_module.run_eval(
        get_settings(),
        run_id="g",
        schema_ids=["fieldservice"],
        systems=["ledgerline", "oneshot"],
        mode=mode,
        models=["target/model"],
        trials=1,
        budget_usd=1.0,
        gold=gold,
    )


def test_a_second_gold_file_is_scored_and_named(isolated: Path, pg_seeded: Engine) -> None:
    first = _run("export", FIXTURE)
    assert first.deferred == {"fieldservice/ledgerline": 2, "fieldservice/oneshot": 2}
    for system, body in (
        (
            "ledgerline",
            {"intent_type": "summary", "entity": "parts", "metrics": [{"agg": "count"}]},
        ),
        ("oneshot", {"sql": "SELECT count(*) FROM parts", "refusal_reason": None}),
    ):
        pending = isolated / "pending" / "fieldservice" / system
        for request_file in pending_requests(pending):
            key = json.loads(request_file.read_text())["key"]
            answer_path(pending, key).write_text(
                json.dumps({"key": key, "simulated_by": "fixture", "response": body})
            )
        store = ReplayStore(isolated / "recordings" / "fieldservice" / f"{system}.jsonl")
        assert len(import_answers(pending, store)) == 2

    result = _run("replay", FIXTURE)
    assert len(result.records) == 4
    assert {r["gold"] for r in result.records} == {"gold-two.jsonl"}
    assert {r["item_id"] for r in result.records} == {"fx-001", "fx-002"}

    report = report_module.build(result)
    Report.model_validate(json.loads(json.dumps(report, default=str)))
    assert report["gold_files"] == ["gold-two.jsonl"]
    assert {row["gold"] for row in report["table"]} == {"gold-two.jsonl"}
    assert [m["gold"] for m in report["misses"]] == ["gold-two.jsonl"]  # fx-002 answered
    md = report_module.render_markdown(report)
    assert "Gold: `gold-two.jsonl`." in md
    table = [line for line in md.splitlines() if line.startswith("| fieldservice |")]
    assert len(table) == 2
    assert all(line.endswith("| gold-two.jsonl |") for line in table)
    assert "`fx-002` (fieldservice, gold-two.jsonl, trial 1)" in md


def test_the_default_gold_keeps_its_checkpoint_keys(isolated: Path) -> None:
    """Runs on the default gold resume from checkpoints written before --gold existed."""
    item = run_module.items_for("fieldservice")[0]
    other = run_module.items_for("fieldservice", FIXTURE)[0]
    assert item.gold == "fieldservice.jsonl"
    assert "|gold=" not in run_module.Task("fieldservice", "m", 1, "ledgerline", item).key
    assert run_module.Task("fieldservice", "m", 1, "ledgerline", other).key.endswith(
        "|gold=gold-two.jsonl"
    )


def test_records_without_a_gold_are_read_as_the_schema_default() -> None:
    record = {
        "schema_id": "spider_car_1",
        "system": "ledgerline",
        "model": "m",
        "trial": 1,
        "item_id": "spider:1",
        "category": "in_schema",
        "outcome": "correct",
        "cost_usd": 0.0,
        "latency_ms": 1.0,
        "error": None,
        "sql": None,
        "detail": {},
        "provenance": {},
    }
    result = run_module.RunResult(
        run_id="t", records=[record], systems=["ledgerline"], models=["m"]
    )
    report = report_module.build(result)
    assert report["table"][0]["gold"] == "spider_ids.json"
    assert report["gold_files"] == ["spider_ids.json"]


def test_gold_needs_exactly_one_schema_and_not_spider(isolated: Path) -> None:
    with pytest.raises(ValueError, match="one schema"):
        run_module.run_eval(
            get_settings(),
            run_id="g",
            schema_ids=["fieldservice", "spider_car_1"],
            systems=["ledgerline"],
            mode="replay",
            models=["m"],
            trials=1,
            budget_usd=0.0,
            gold=FIXTURE,
        )
    with pytest.raises(ValueError, match="Spider"):
        run_module.items_for("spider_car_1", FIXTURE)


def test_the_cli_passes_gold_through(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, object] = {}

    def fake_run_eval(settings: object, **kwargs: object) -> run_module.RunResult:
        seen.update(kwargs)
        raise SystemExit(0)

    monkeypatch.setattr(run_module, "run_eval", fake_run_eval)
    result = CliRunner().invoke(
        app, ["eval", "--schema", "fieldservice", "--gold", str(FIXTURE), "--mode", "replay"]
    )
    assert result.exit_code == 0, result.output
    assert seen["gold"] == FIXTURE
