"""Starter questions on a confirmed workspace: made from its own tables and columns by
templates, with no model call, and each one a question the grammar can answer."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from askwell.api import create_app
from askwell.config import Settings, get_settings
from askwell.core.intent import Intent
from askwell.core.registry import load_registry
from askwell.core.sqlbuild import build
from askwell.core.validate import validate
from askwell.workspace.api import HEADER, WorkspaceApp
from askwell.workspace.ask import local_now, workspace_target
from askwell.workspace.fields import load_draft
from askwell.workspace.starters import MAX_STARTERS, starters
from askwell.workspace.store import WorkspaceStore
from tests.workspace.conftest import FakeClock, csv_file, upload, upload_sample
from tests.workspace.fake_model import FakeModel, fake_service


@pytest.fixture
def model() -> FakeModel:
    return FakeModel()


@pytest.fixture
def client(store: WorkspaceStore, model: FakeModel) -> Iterator[TestClient]:
    settings: Settings = get_settings()
    app = create_app(service=fake_service(settings, model), workspaces=WorkspaceApp(store))
    with TestClient(app) as c:
        yield c


def confirmed(
    client: TestClient, edits: dict[str, Any] | None = None, sample: bool = True
) -> dict[str, str]:
    headers = {HEADER: client.post("/api/workspaces", json={}).json()["id"]}
    if sample:
        upload_sample(client, headers)
    else:
        item = csv_file("notes.csv", "id,author,topic\n1,Ana,billing\n2,Bo,billing\n3,Cy,setup\n")
        assert upload(client, headers, item.name, item.data) == 200
    assert client.post("/api/workspace/check", headers=headers).json()["state"] == "checked"
    response = client.post("/api/workspace/confirm", json={"fields": edits or {}}, headers=headers)
    assert response.json()["state"] == "confirmed"
    return headers


def runs(
    store: WorkspaceStore, clock: FakeClock, headers: dict[str, str], intent: Intent
) -> list[Any]:
    """Parse, validate, build and run one starter's intent on the workspace's data."""
    parsed = Intent.model_validate_json(intent.model_dump_json())
    workspace = store.open(headers[HEADER], touch=False)
    with workspace_target(workspace, clock) as target:
        result = validate(parsed, target.registry, now=target.now, allow_draft=False)
        assert result.ok, (intent, result.codes)
        assert result.plan is not None
        with target.engine.connect() as conn:
            return list(conn.execute(build(result.plan)).fetchall())


def made(store: WorkspaceStore, clock: FakeClock, headers: dict[str, str]) -> list[Any]:
    workspace = store.open(headers[HEADER], touch=False)
    _, info = load_draft(workspace)
    now = local_now(workspace.meta.time_zone, clock)
    return starters(load_registry(workspace.registry_path), info, now)


def test_the_sample_gets_three_to_five_starters_with_no_model_call(
    client: TestClient, model: FakeModel
) -> None:
    headers = confirmed(client)
    response = client.get("/api/workspace/starters", headers=headers)
    assert response.status_code == 200
    questions = response.json()["questions"]
    assert 3 <= len(questions) <= MAX_STARTERS == 5
    assert len(set(questions)) == len(questions)
    assert all(isinstance(q, str) and q.endswith("?") for q in questions)
    assert model.calls == []


def test_every_starter_parses_validates_builds_and_runs(
    client: TestClient, store: WorkspaceStore, clock: FakeClock
) -> None:
    headers = confirmed(client)
    found = made(store, clock, headers)
    assert [s.question for s in found] == client.get(
        "/api/workspace/starters", headers=headers
    ).json()["questions"]
    for starter in found:
        assert runs(store, clock, headers, starter.intent), starter.question


def test_the_templates_cover_a_category_count_a_monthly_sum_and_a_top_five(
    client: TestClient, store: WorkspaceStore, clock: FakeClock
) -> None:
    intents = [s.intent for s in made(store, clock, confirmed(client))]
    assert any(
        i.intent_type == "grouped_summary"
        and i.metrics[0].agg == "count"
        and i.group_by
        and i.group_by[0].grain is None
        for i in intents
    )
    assert any(
        i.metrics and i.metrics[0].agg == "sum" and i.group_by and i.group_by[0].grain == "month"
        for i in intents
    )
    assert any(
        i.intent_type == "row_list" and i.limit == 5 and i.order_by[0].direction == "desc"
        for i in intents
    )


def test_hidden_fields_never_appear(
    client: TestClient, store: WorkspaceStore, clock: FakeClock
) -> None:
    hidden = ["orders.shipping_cost", "orders.status", "products.unit_price"]
    headers = confirmed(client, {key: {"hidden": True} for key in hidden})
    found = made(store, clock, headers)
    assert found
    for starter in found:
        dumped = starter.intent.model_dump_json()
        for key in hidden:
            name = key.split(".")[1]
            assert f'"{name}"' not in dumped, starter.question
            assert f".{name}" not in dumped, starter.question
            assert name.replace("_", " ") not in starter.question
        assert runs(store, clock, headers, starter.intent)


def test_a_text_only_table_still_gets_answerable_starters(
    client: TestClient, store: WorkspaceStore, clock: FakeClock
) -> None:
    headers = confirmed(client, sample=False)
    found = made(store, clock, headers)
    assert found
    for starter in found:
        assert runs(store, clock, headers, starter.intent)


def test_starters_wait_for_confirm(client: TestClient) -> None:
    headers = {HEADER: client.post("/api/workspaces", json={}).json()["id"]}
    upload_sample(client, headers)
    client.post("/api/workspace/check", headers=headers)
    assert client.get("/api/workspace/starters", headers=headers).status_code == 409
