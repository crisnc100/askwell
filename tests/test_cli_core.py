"""CLI: registry init / check and compile (validate + build), no LLM involved."""

from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import Engine
from typer.testing import CliRunner

from ledgerline.cli import app
from tests.core.conftest import FIELDSERVICE_REGISTRY

runner = CliRunner()


def test_registry_init_then_check(sqlite_fieldservice: Engine, tmp_path: Path) -> None:
    out = tmp_path / "fs.yaml"
    result = runner.invoke(
        app, ["registry", "init", str(sqlite_fieldservice.url), "-o", str(out), "--values"]
    )
    assert result.exit_code == 0, result.output
    assert "8 entities, 6 relationships (draft)" in result.output
    assert "writable" in result.output  # the fixture file is writable: warned
    checked = runner.invoke(app, ["registry", "check", str(out)])
    assert checked.exit_code == 0
    assert "2 hidden fields, DRAFT" in checked.output


def test_compile_prints_sql_and_params(tmp_path: Path) -> None:
    intent = tmp_path / "intent.json"
    intent.write_text(
        json.dumps(
            {
                "intent_type": "summary",
                "entity": "invoices",
                "metrics": [{"agg": "count"}],
                "filters": [{"field": "status", "op": "eq", "value": "Overdue"}],
            }
        )
    )
    result = runner.invoke(
        app, ["compile", "--registry", str(FIELDSERVICE_REGISTRY), "--intent", str(intent)]
    )
    assert result.exit_code == 0, result.output
    assert "FROM invoices AS t0" in result.output
    assert '"overdue"' in result.output  # canonical value, in params only
    assert "'overdue'" not in result.output


def test_compile_reports_issues_and_refusals(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"intent_type": "row_list", "entity": "users", "select": ["email"]}))
    result = runner.invoke(
        app, ["compile", "--registry", str(FIELDSERVICE_REGISTRY), "--intent", str(bad)]
    )
    assert result.exit_code == 1
    assert "hidden_field at select[0]" in result.output
    refusal = tmp_path / "no.json"
    refusal.write_text(json.dumps({"intent_type": "unanswerable", "unanswerable_reason": "nope"}))
    result = runner.invoke(
        app, ["compile", "--registry", str(FIELDSERVICE_REGISTRY), "--intent", str(refusal)]
    )
    assert result.exit_code == 0
    assert "refusal: nope" in result.output
