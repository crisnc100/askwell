"""L21: every server-side limit has a test. The column, row and cell-length limits are
Check rules (test_too_many_columns, test_too_many_rows, test_cell_too_long and
test_cell_past_the_csv_reader_limit in test_check_rules.py); the rest are here."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ledgerline.api import create_app
from ledgerline.workspace.api import HEADER, WorkspaceApp
from ledgerline.workspace.limits import Limits, RateLimiter
from ledgerline.workspace.store import (
    DiskFullError,
    FileTooLargeError,
    WorkspaceStore,
)
from tests.workspace.conftest import FakeClock, _NoService, new_workspace, upload


def app_client(store: WorkspaceStore, trust_proxy: bool = False) -> TestClient:
    workspaces = WorkspaceApp(store, trust_proxy=trust_proxy)
    return TestClient(create_app(service=_NoService(), workspaces=workspaces))  # type: ignore[arg-type]


@pytest.fixture
def small(tmp_path: Path, clock: FakeClock) -> WorkspaceStore:
    limits = Limits(
        max_file_bytes=1000,
        max_files=2,
        disk_cap_bytes=5000,
        workspaces_per_ip=2,
        uploads_per_hour=4,
    )
    return WorkspaceStore(tmp_path / "ws", limits, clock)


@pytest.fixture
def small_client(small: WorkspaceStore) -> Iterator[TestClient]:
    with app_client(small) as client:
        yield client


class Chunks:
    """An upload body that counts how much of it the server read."""

    def __init__(self, size: int, count: int) -> None:
        self.size = size
        self.count = count
        self.read = 0

    async def __aiter__(self) -> AsyncIterator[bytes]:
        for _ in range(self.count):
            self.read += 1
            yield b"x" * self.size


async def test_file_size_is_enforced_while_streaming(small: WorkspaceStore) -> None:
    workspace = small.create("1.1.1.1")
    body = Chunks(size=300, count=100)
    with pytest.raises(FileTooLargeError, match="at most 1,000 bytes"):
        await small.upload(workspace, "big.csv", body.__aiter__())
    assert body.read == 4  # stopped at the first chunk past the limit
    assert list(workspace.uploads.iterdir()) == []


def test_declared_size_is_refused_before_reading(small_client: TestClient) -> None:
    headers = new_workspace(small_client)
    assert upload(small_client, headers, "big.csv", b"x" * 1001) == 413


def test_file_count_limit(small_client: TestClient) -> None:
    headers = new_workspace(small_client)
    assert upload(small_client, headers, "a.csv", b"id\n1\n") == 200
    assert upload(small_client, headers, "b.csv", b"id\n1\n") == 200
    assert upload(small_client, headers, "c.csv", b"id\n1\n") == 409
    assert upload(small_client, headers, "a.csv", b"id\n2\n") == 200  # a replacement


async def test_disk_cap_while_streaming(small: WorkspaceStore) -> None:
    workspace = small.create("1.1.1.1")
    (small.root / "filler").write_bytes(b"x" * 4800)
    body = Chunks(size=100, count=9)
    with pytest.raises(DiskFullError):
        await small.upload(workspace, "a.csv", body.__aiter__())
    assert body.read < 9


def test_disk_cap_before_loading(small: WorkspaceStore) -> None:
    workspace = small.create("1.1.1.1")
    (workspace.uploads / "f1.csv").write_bytes(b"id\n1\n")
    from ledgerline.workspace.store import FileEntry

    workspace.meta.files.append(FileEntry("a.csv", "f1.csv", 5, workspace.meta.created_at))
    workspace.save()
    (small.root / "filler").write_bytes(b"x" * 4990)
    with pytest.raises(DiskFullError):
        small.check(workspace)
    assert not workspace.db_path.exists()


def test_live_workspaces_per_ip(small_client: TestClient, clock: FakeClock) -> None:
    new_workspace(small_client)
    new_workspace(small_client)
    third = small_client.post("/api/workspaces", json={})
    assert third.status_code == 429
    assert "already have 2 workspaces" in third.json()["detail"]
    clock.advance(days=8)  # both expire
    new_workspace(small_client)


def test_deleting_frees_a_workspace_slot(small_client: TestClient) -> None:
    first = new_workspace(small_client)
    new_workspace(small_client)
    small_client.delete("/api/workspace", headers=first)
    new_workspace(small_client)


def test_upload_rate_limit_per_ip(small_client: TestClient) -> None:
    headers = new_workspace(small_client)
    codes = [upload(small_client, headers, "a.csv", b"id\n1\n") for _ in range(5)]
    assert codes == [200, 200, 200, 200, 429]


def test_rate_limiter_window_slides() -> None:
    now = [0.0]
    limiter = RateLimiter(2, 60.0, clock=lambda: now[0])
    assert [limiter.allow("a"), limiter.allow("a"), limiter.allow("a")] == [True, True, False]
    assert limiter.allow("b")
    now[0] = 60.0
    assert limiter.allow("a")


def test_forwarded_for_is_ignored_unless_trusted(small: WorkspaceStore) -> None:
    spoofed = {"X-Forwarded-For": "9.9.9.9"}
    with app_client(small) as client:
        client.post("/api/workspaces", json={}, headers=spoofed)
        client.post("/api/workspaces", json={}, headers={"X-Forwarded-For": "8.8.8.8"})
        # Both counted against the real client address, so the cap is reached.
        assert client.post("/api/workspaces", json={}, headers=spoofed).status_code == 429


def test_forwarded_for_is_used_behind_a_trusted_proxy(small: WorkspaceStore) -> None:
    with app_client(small, trust_proxy=True) as client:
        for _ in range(2):
            ok = client.post("/api/workspaces", json={}, headers={"X-Forwarded-For": "1.1.1.1"})
            assert ok.status_code == 201
        other = client.post(
            "/api/workspaces", json={}, headers={"X-Forwarded-For": "6.6.6.6, 2.2.2.2"}
        )
        assert other.status_code == 201
        full = client.post("/api/workspaces", json={}, headers={"X-Forwarded-For": "1.1.1.1"})
        assert full.status_code == 429


def test_upload_after_confirm_is_refused_over_http(
    small_client: TestClient, small: WorkspaceStore
) -> None:
    headers = new_workspace(small_client)
    workspace = small.open(headers[HEADER])
    workspace.meta.state = "confirmed"
    workspace.save()
    response = small_client.put(
        "/api/workspace/files", params={"name": "a.csv"}, content=b"id\n1\n", headers=headers
    )
    assert response.status_code == 409
    assert "Start a new workspace" in response.json()["detail"]


def test_trusted_proxy_without_the_header_uses_the_peer_address(small: WorkspaceStore) -> None:
    with app_client(small, trust_proxy=True) as client:
        client.post("/api/workspaces", json={})
        client.post("/api/workspaces", json={}, headers={"X-Forwarded-For": " "})
        assert client.post("/api/workspaces", json={}).status_code == 429
