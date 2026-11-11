"""The Results page's routes serve only the committed reports and triage files, by the
names found in their folders."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from ledgerline.api import create_app
from ledgerline.bench import results
from ledgerline.workspace.api import WorkspaceApp
from ledgerline.workspace.store import WorkspaceStore
from tests.workspace.conftest import _NoService


def _report(run_id: str, schemas: list[str]) -> dict[str, object]:
    return {"run_id": run_id, "simulation": None, "table": [{"schema": s} for s in schemas]}


def _client(tmp_path: Path) -> TestClient:
    reports, triage = tmp_path / "reports", tmp_path / "triage"
    reports.mkdir()
    triage.mkdir()
    (reports / "small.json").write_text(json.dumps(_report("small", ["a"])))
    (reports / "big.json").write_text(json.dumps(_report("big", ["a", "b"])))
    (triage / "a.yaml").write_text("x-1: {tag: misread, note: n}\n")
    (tmp_path / "secret.json").write_text("{}")
    (tmp_path / "secret.yaml").write_text("no")
    app = FastAPI()
    results.install(app, reports, triage)
    return TestClient(app)


def test_reports_are_listed_with_the_widest_first(tmp_path: Path) -> None:
    listed = _client(tmp_path).get("/api/reports").json()
    assert [r["id"] for r in listed] == ["big", "small"]
    assert listed[0]["schemas"] == ["a", "b"]


def test_a_report_says_which_schemas_have_a_triage_file(tmp_path: Path) -> None:
    body = _client(tmp_path).get("/api/reports/big").json()
    assert body["run_id"] == "big"
    assert body["triage_files"] == ["a"]


def test_triage_is_served_as_text(tmp_path: Path) -> None:
    response = _client(tmp_path).get("/api/triage/a")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert "misread" in response.text


def test_unknown_or_crafted_names_are_not_found(tmp_path: Path) -> None:
    client = _client(tmp_path)
    for path in (
        "/api/reports/missing",
        "/api/reports/..%2Fsecret",
        "/api/reports/../secret",
        "/api/triage/..%2Fsecret",
        "/api/triage/b",
    ):
        assert client.get(path).status_code == 404, path


def test_the_app_serves_every_committed_report(tmp_path: Path) -> None:
    workspaces = WorkspaceApp(WorkspaceStore(tmp_path / "ws"))
    app = create_app(service=_NoService(), workspaces=workspaces, web_dir=tmp_path / "none")  # type: ignore[arg-type]
    with TestClient(app) as client:
        listed = client.get("/api/reports").json()
        assert listed[0]["id"] == "sim-1"
        for summary in listed:
            body = client.get(f"/api/reports/{summary['id']}").json()
            assert body["run_id"] == summary["id"]
            for schema in body["triage_files"]:
                assert client.get(f"/api/triage/{schema}").status_code == 200
