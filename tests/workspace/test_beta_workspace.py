"""L26 on uploaded workspaces: with the kill switch on or the daily cap reached, a
workspace ask gets the same plain message as the demo, never a 500 or the generic
"try again"."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from ledgerline.api import create_app
from ledgerline.config import Settings, get_settings
from ledgerline.llm.daily import CAP_REACHED, DailyCapReachedError
from ledgerline.llm.errors import LIVE_ANSWERS_OFF, LiveAnswersOffError
from ledgerline.workspace.api import WorkspaceApp
from ledgerline.workspace.store import WorkspaceStore
from tests.workspace.fake_model import FakeModel, fake_service
from tests.workspace.test_confirm_ask import checked, confirm


@pytest.fixture
def settings() -> Settings:
    return get_settings()


@pytest.fixture
def model() -> FakeModel:
    return FakeModel()


@pytest.fixture
def client(store: WorkspaceStore, settings: Settings, model: FakeModel) -> Iterator[TestClient]:
    app = create_app(
        service=fake_service(settings, model), workspaces=WorkspaceApp(store), invite_codes=[]
    )
    with TestClient(app) as c:
        yield c


@pytest.mark.parametrize(
    ("error", "message"),
    [(LiveAnswersOffError(), LIVE_ANSWERS_OFF), (DailyCapReachedError(1, 1, 1), CAP_REACHED)],
)
def test_a_workspace_ask_says_live_answers_are_unavailable(
    client: TestClient, model: FakeModel, error: Exception, message: str
) -> None:
    def refuse(_question: str) -> dict[str, Any]:
        raise error

    model.answers = refuse
    headers = checked(client)
    confirm(client, headers, {})
    response = client.post("/api/workspace/ask", json={"question": "q"}, headers=headers)
    assert response.status_code == 503
    assert response.json() == {"detail": message}
