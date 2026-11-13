"""An end-to-end eval run in a temp directory: export, (synthetic) answers, import, replay,
score, report. The answers here are fixtures for the mechanism, never committed."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest
from sqlalchemy import Engine

from askwell.bench import report as report_module
from askwell.bench import run as run_module
from askwell.config import get_settings
from askwell.llm.replay import ReplayStore
from askwell.llm.simulate import answer_path, import_answers, pending_requests


@pytest.fixture
def isolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(run_module, "RUNS_DIR", tmp_path / "runs")
    monkeypatch.setattr(run_module, "EVAL_RECORDINGS", tmp_path / "recordings")
    monkeypatch.setattr(run_module, "EVAL_PENDING", tmp_path / "pending")
    monkeypatch.setattr(report_module, "TRIAGE_DIR", tmp_path / "triage")
    return tmp_path


def _run(mode: str):
    return run_module.run_eval(
        get_settings(),
        run_id="t",
        schema_ids=["fieldservice"],
        systems=["ledgerline", "oneshot"],
        mode=mode,
        models=["target/model"],
        trials=1,
        budget_usd=1.0,
    )


def _answer_all(pending: Path, askwell: dict[str, object], oneshot: dict[str, object]) -> None:
    for request_file in pending_requests(pending):
        request = json.loads(request_file.read_text())
        body = askwell if request["response_schema_name"] == "Intent" else oneshot
        answer_path(pending, request["key"]).write_text(
            json.dumps({"key": request["key"], "simulated_by": "fixture", "response": body})
        )


def test_export_import_replay_score_report(isolated: Path, pg_seeded: Engine) -> None:
    first = _run("export")
    assert first.records == []
    assert first.deferred == {"fieldservice/ledgerline": 67, "fieldservice/oneshot": 67}
    assert run_module.pending_counts() == {
        "fieldservice/ledgerline": 67,
        "fieldservice/oneshot": 67,
    }

    # Every question answered the same way: askwell refuses, oneshot counts invoices.
    _answer_all(
        isolated / "pending" / "fieldservice" / "ledgerline",
        {"intent_type": "unanswerable", "unanswerable_reason": "fixture"},
        {},
    )
    _answer_all(
        isolated / "pending" / "fieldservice" / "oneshot",
        {},
        {"sql": "SELECT count(*) FROM invoices", "refusal_reason": None},
    )
    for system in ("ledgerline", "oneshot"):
        store = ReplayStore(isolated / "recordings" / "fieldservice" / f"{system}.jsonl")
        assert len(import_answers(isolated / "pending" / "fieldservice" / system, store)) == 67

    result = _run("replay")
    assert len(result.records) == 134
    assert result.deferred == {}
    by_system: dict[str, list[str]] = {}
    for record in result.records:
        by_system.setdefault(record["system"], []).append(record["outcome"])
    assert set(by_system["ledgerline"]) == {"refused"}
    assert "wrong" in by_system["oneshot"]  # rows for refusal items, wrong counts elsewhere

    report = report_module.build(result)
    assert report["simulation"] == (
        "Model responses simulated by fixture, standing in for target/model. "
        "This is not an OpenRouter measurement."
    )
    rows = {row["system"]: row for row in report["table"]}
    assert rows["ledgerline"]["refusal_recall"]["n"] == 24
    assert rows["ledgerline"]["execution_accuracy"]["n"] == 0
    assert rows["oneshot"]["refusal_recall"]["n"] == 0
    assert len(report["misses"]) == 43  # every in_schema item refused
    assert {m["tag"] for m in report["misses"]} == {"untriaged"}
    assert report["notes"][0] == report_module.SQL_AGENT_NOT_RUN
    assert any(n.startswith("One target model (target/model)") for n in report["notes"])
    assert any(n.startswith("Trials: 1.") for n in report["notes"])
    md = report_module.render_markdown(report)
    assert md.splitlines()[0].startswith("> **Model responses simulated by fixture")
    assert "| fieldservice | ledgerline | target/model | 1 |" in md

    # Resuming the same run finishes nothing new and keeps every record.
    again = _run("replay")
    assert len(again.records) == 134


def test_sql_agent_is_not_built_yet(isolated: Path) -> None:
    with pytest.raises(NotImplementedError, match="sql_agent"):
        run_module.run_eval(
            get_settings(),
            run_id="t",
            schema_ids=["fieldservice"],
            systems=["sql_agent"],
            mode="replay",
            models=["m"],
            trials=1,
            budget_usd=1.0,
        )


def test_unknown_system_and_schema(isolated: Path) -> None:
    with pytest.raises(ValueError, match="unknown system"):
        run_module.run_eval(
            get_settings(),
            run_id="t",
            schema_ids=["fieldservice"],
            systems=["magic"],
            mode="replay",
            models=["m"],
            trials=1,
            budget_usd=1.0,
        )
    with pytest.raises(ValueError, match="unknown schema"):
        run_module.run_eval(
            get_settings(),
            run_id="t",
            schema_ids=["nope"],
            systems=["oneshot"],
            mode="replay",
            models=["m"],
            trials=1,
            budget_usd=1.0,
        )


def test_triage_tags_are_checked(isolated: Path) -> None:
    (isolated / "triage").mkdir()
    (isolated / "triage" / "fieldservice.yaml").write_text("fs-001: {tag: vibes}\n")
    with pytest.raises(ValueError, match="vibes"):
        report_module.load_triage("fieldservice")


def test_changing_the_prompt_or_registry_never_resumes_old_results(
    isolated: Path, pg_seeded: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A checkpoint record is only reused for the same prompt version and registry; any
    change makes those tasks run again (here: exported again)."""
    from askwell.pipeline import service as service_module

    _run("export")
    _answer_all(
        isolated / "pending" / "fieldservice" / "ledgerline",
        {"intent_type": "unanswerable", "unanswerable_reason": "fixture"},
        {},
    )
    _answer_all(
        isolated / "pending" / "fieldservice" / "oneshot",
        {},
        {"sql": "SELECT 1", "refusal_reason": None},
    )
    for system in ("ledgerline", "oneshot"):
        store = ReplayStore(isolated / "recordings" / "fieldservice" / f"{system}.jsonl")
        import_answers(isolated / "pending" / "fieldservice" / system, store)
    assert len(_run("export").records) == 134

    # A separate MonkeyPatch: undoing it must not undo the fixture's directory patches,
    # or the rest of the test would write into the real evals/ directories.
    with pytest.MonkeyPatch.context() as prompt_patch:
        prompt_patch.setattr(service_module, "PROMPT_VERSION", "interpret-v999")
        changed_prompt = _run("export")
    assert changed_prompt.deferred == {"fieldservice/ledgerline": 67}
    assert {r["system"] for r in changed_prompt.records} == {"oneshot"}
    assert isolated / "runs" == run_module.RUNS_DIR
    assert isolated / "pending" == run_module.EVAL_PENDING

    edited = isolated / "fieldservice.yaml"
    from tests.core.conftest import FIELDSERVICE_REGISTRY

    edited.write_text(FIELDSERVICE_REGISTRY.read_text().replace("Parts catalogue.", "Parts list."))
    real = run_module._schemas

    def with_edited_registry(settings, schema_ids):
        schemas, hashes = real(settings, schema_ids)
        schemas["fieldservice"] = replace(schemas["fieldservice"], registry_path=edited)
        return schemas, hashes

    monkeypatch.setattr(run_module, "_schemas", with_edited_registry)
    changed_registry = _run("export")
    assert changed_registry.records == []
    assert sum(changed_registry.deferred.values()) == 134
