"""Who a request comes from, and what a request must look like to create a workspace."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from ledgerline.api import create_app
from ledgerline.workspace.api import WorkspaceApp
from ledgerline.workspace.limits import Limits
from ledgerline.workspace.store import WorkspaceStore
from tests.workspace.conftest import FakeClock, _NoService


def _client(tmp_path: Path, clock: FakeClock, trust_proxy: bool) -> TestClient:
    store = WorkspaceStore(tmp_path / "ws", Limits(workspaces_per_ip=1), clock)
    app = create_app(service=_NoService(), workspaces=WorkspaceApp(store, trust_proxy=trust_proxy))  # type: ignore[arg-type]
    return TestClient(app)


def test_the_proxy_address_is_the_last_value_across_every_header_line(
    tmp_path: Path, clock: FakeClock
) -> None:
    with _client(tmp_path, clock, trust_proxy=True) as client:
        # The client wrote the first line; the proxy appended the second.
        two_lines = [("X-Forwarded-For", "9.9.9.9"), ("X-Forwarded-For", "1.1.1.1")]
        assert client.post("/api/workspaces", json={}, headers=two_lines).status_code == 201
        again = {"X-Forwarded-For": "1.1.1.1"}
        assert client.post("/api/workspaces", json={}, headers=again).status_code == 429
        appended = [("X-Forwarded-For", "1.1.1.1"), ("X-Forwarded-For", "8.8.8.8")]
        assert client.post("/api/workspaces", json={}, headers=appended).status_code == 201


def test_creating_a_workspace_needs_a_json_request(tmp_path: Path, clock: FakeClock) -> None:
    """A cross-site page can send a plain form or an empty POST without asking the
    browser first; it cannot send JSON that way."""
    with _client(tmp_path, clock, trust_proxy=False) as client:
        assert client.post("/api/workspaces").status_code == 415
        form = {"content-type": "application/x-www-form-urlencoded"}
        assert client.post("/api/workspaces", content=b"a=1", headers=form).status_code == 415
        plain = {"content-type": "text/plain"}
        assert client.post("/api/workspaces", content=b"{}", headers=plain).status_code == 415
        assert client.post("/api/workspaces", json={}).status_code == 201
