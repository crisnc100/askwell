from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient

from ledgerline.api import create_app
from ledgerline.workspace.api import FILE_HEADER, HEADER, WorkspaceApp
from ledgerline.workspace.check import CheckResult, UploadedFile, check_files
from ledgerline.workspace.limits import Limits
from ledgerline.workspace.store import WorkspaceStore

ROOT = Path(__file__).resolve().parents[2]
SAMPLE = ROOT / "web" / "public" / "sample"


class FakeClock:
    def __init__(self, start: datetime | None = None) -> None:
        self.now = start or datetime(2026, 11, 11, 15, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **delta: float) -> None:
        self.now += timedelta(**delta)


def csv_file(name: str, text: str) -> UploadedFile:
    return UploadedFile(name, text.encode("utf-8"))


def check(*files: UploadedFile, limits: Limits | None = None) -> CheckResult:
    return check_files(list(files), limits)


def sample_files() -> list[UploadedFile]:
    return [UploadedFile(p.name, p.read_bytes()) for p in sorted(SAMPLE.glob("*.csv"))]


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def store(tmp_path: Path, clock: FakeClock) -> WorkspaceStore:
    return WorkspaceStore(tmp_path / "workspaces", Limits(), clock)


@pytest.fixture
def client(store: WorkspaceStore) -> Iterator[TestClient]:
    app = create_app(service=_NoService(), workspaces=WorkspaceApp(store))  # type: ignore[arg-type]
    with TestClient(app) as c:
        yield c


class _NoService:
    """Stands in for the demo ask service where a test needs only the workspace routes."""

    gateway = None

    def close(self) -> None:
        pass


def new_workspace(client: TestClient) -> dict[str, str]:
    response = client.post("/api/workspaces", json={})
    assert response.status_code == 201, response.text
    return {HEADER: response.json()["id"]}


def upload(client: TestClient, headers: dict[str, str], name: str, data: bytes) -> int:
    response = client.put(
        "/api/workspace/files", content=data, headers={**headers, FILE_HEADER: quote(name)}
    )
    return response.status_code


def upload_sample(client: TestClient, headers: dict[str, str]) -> None:
    for item in sample_files():
        assert upload(client, headers, item.name, item.data) == 200
