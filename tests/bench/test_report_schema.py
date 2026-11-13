"""L25: the committed report JSON Schema matches the models it is generated from, and
every committed report, plus a freshly built one, validates against them."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from askwell.bench import report as report_module
from askwell.bench.report_schema import SCHEMA_FILE, Report, json_schema
from askwell.bench.run import RunResult

COMMITTED = sorted(report_module.REPORTS_DIR.glob("*.json"))


def test_the_committed_schema_file_is_generated_from_the_models() -> None:
    assert SCHEMA_FILE.read_text(encoding="utf-8") == json_schema()


def test_there_are_committed_reports() -> None:
    assert {p.stem for p in COMMITTED} >= {"sim-1", "replay-fieldservice"}


@pytest.mark.parametrize("path", COMMITTED, ids=[p.stem for p in COMMITTED])
def test_every_committed_report_validates(path: Path) -> None:
    report = Report.model_validate(json.loads(path.read_text(encoding="utf-8")))
    assert report.run_id == path.stem
    assert report.table


def _record(schema: str, system: str, item: str, category: str, outcome: str) -> dict[str, object]:
    return {
        "schema_id": schema,
        "system": system,
        "model": "m",
        "trial": 1,
        "item_id": item,
        "category": category,
        "outcome": outcome,
        "cost_usd": 0.0,
        "latency_ms": 1.0,
        "error": None,
        "sql": None,
        "detail": {"refusal": "no" if outcome == "refused" else None, "issue_codes": []},
        "provenance": {"simulated_by": "stand-in", "standing_in_for": "m"},
    }


def test_a_freshly_built_report_validates() -> None:
    result = RunResult(
        run_id="t",
        records=[
            _record("fieldservice", "ledgerline", "fs-001", "in_schema", "wrong"),
            _record("fieldservice", "oneshot", "fs-001", "in_schema", "correct"),
            _record("fieldservice", "ledgerline", "fs-050", "out_of_schema", "refused"),
        ],
        systems=["ledgerline", "oneshot"],
        models=["m"],
    )
    built = report_module.build(result)
    report = Report.model_validate(json.loads(json.dumps(built, default=str)))
    assert report.simulation is not None
    assert [w.item_id for w in report.baseline_wins] == ["fs-001"]


def test_the_schema_refuses_an_unknown_field_and_a_bad_rate() -> None:
    data = json.loads(COMMITTED[0].read_text(encoding="utf-8"))
    with pytest.raises(ValidationError):
        Report.model_validate({**data, "surprise": 1})
    row = {**data["table"][0], "coverage": {"n": 1, "of": 1, "rate": 1.5, "ci95": None}}
    with pytest.raises(ValidationError):
        Report.model_validate({**data, "table": [row]})
