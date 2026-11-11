"""Workspace lifecycle, isolation, deletion and the sweep (L18)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from ledgerline.workspace.api import HEADER
from ledgerline.workspace.store import (
    WorkspaceStore,
    WrongStateError,
    check_file_name,
    parse_workspace_id,
)
from tests.workspace.conftest import FakeClock, new_workspace, upload, upload_sample


def test_states_move_new_checked_and_back_on_upload(client: TestClient) -> None:
    headers = new_workspace(client)
    assert client.get("/api/workspace", headers=headers).json()["state"] == "new"
    upload_sample(client, headers)
    body = client.post("/api/workspace/check", headers=headers).json()
    assert body["state"] == "checked"
    assert body["check"]["ok"] is True
    assert upload(client, headers, "extra.csv", b"id\n1\n") == 200
    body = client.get("/api/workspace", headers=headers).json()
    assert body["state"] == "new"
    assert body["check"] is None


def test_same_name_upload_replaces_the_file(client: TestClient) -> None:
    headers = new_workspace(client)
    assert upload(client, headers, "items.csv", b"id,label\n1,a\n") == 200
    assert upload(client, headers, "items.csv", b"id,label\n1,a\n2,b\n") == 200
    files = client.get("/api/workspace", headers=headers).json()["files"]
    assert files == [{"name": "items.csv", "bytes": len(b"id,label\n1,a\n2,b\n")}]


def test_a_failing_file_blocks_loading_and_names_its_fix(
    client: TestClient, store: WorkspaceStore
) -> None:
    headers = new_workspace(client)
    upload_sample(client, headers)
    assert upload(client, headers, "visits.csv", b"id,day\n1,3/4/25\n") == 200
    body = client.post("/api/workspace/check", headers=headers).json()
    assert body["state"] == "new"
    assert body["check"]["ok"] is False
    bad = next(f for f in body["check"]["files"] if f["name"] == "visits.csv")
    assert bad["problems"][0]["fix"] == "use 2025-03-04 (if it means March 4, 2025)"
    assert not (store.root / headers[HEADER] / "data.sqlite").exists()


def test_remove_one_file_then_check_again(client: TestClient) -> None:
    headers = new_workspace(client)
    upload_sample(client, headers)
    assert upload(client, headers, "visits.csv", b"id,day\n1,3/4/25\n") == 200
    client.post("/api/workspace/check", headers=headers)
    response = client.delete("/api/workspace/files", params={"name": "visits.csv"}, headers=headers)
    assert response.status_code == 200
    assert client.post("/api/workspace/check", headers=headers).json()["state"] == "checked"
    missing = client.delete("/api/workspace/files", params={"name": "nope.csv"}, headers=headers)
    assert missing.status_code == 404


def test_upload_after_confirm_is_refused(store: WorkspaceStore) -> None:
    workspace = store.create("1.2.3.4")
    workspace.meta.state = "confirmed"
    workspace.save()
    opened = store.open(workspace.id)
    with pytest.raises(WrongStateError, match="Start a new workspace"):
        store.remove_file(opened, "x.csv")
    with pytest.raises(WrongStateError):
        store.check(opened)


def test_check_needs_a_file(client: TestClient) -> None:
    headers = new_workspace(client)
    response = client.post("/api/workspace/check", headers=headers)
    assert response.status_code == 409
    assert response.json() == {"detail": "Upload at least one CSV file first."}


def test_workspace_b_cannot_read_a(client: TestClient) -> None:
    a = new_workspace(client)
    b = new_workspace(client)
    upload_sample(client, a)
    assert client.post("/api/workspace/check", headers=a).json()["state"] == "checked"
    seen_by_b = client.get("/api/workspace", headers=b).json()
    assert seen_by_b["id"] == b[HEADER]
    assert seen_by_b["files"] == []
    assert seen_by_b["check"] is None


@pytest.mark.parametrize(
    "crafted",
    [
        "../" + "a" * 29,
        "a" * 31 + "/",
        "..",
        "A" * 32,
        "a" * 33,
        "%2e%2e%2f" + "a" * 23,
        "a" * 31 + "\x00",
        "",
    ],
)
def test_crafted_ids_are_refused_before_any_file_access(
    client: TestClient, crafted: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    touched: list[str] = []
    monkeypatch.setattr(WorkspaceStore, "_read_meta", lambda _self, wid: touched.append(wid))
    for method, path in (
        ("GET", "/api/workspace"),
        ("POST", "/api/workspace/check"),
        ("DELETE", "/api/workspace"),
    ):
        response = client.request(method, path, headers={HEADER: crafted})
        assert response.status_code == 400, (method, crafted)
        assert response.json() == {"detail": "That is not a workspace link."}
    assert touched == []


def test_missing_header_is_refused(client: TestClient) -> None:
    assert client.get("/api/workspace").status_code == 400


def test_unknown_id_is_not_found(client: TestClient) -> None:
    response = client.get("/api/workspace", headers={HEADER: "0" * 32})
    assert response.status_code == 404


def test_ids_are_128_random_bits(store: WorkspaceStore) -> None:
    ids = {store.create(f"10.0.0.{i}").id for i in range(5)}
    assert len(ids) == 5
    assert all(parse_workspace_id(i) == i and len(i) == 32 for i in ids)


@pytest.mark.parametrize(
    "name",
    ["../x.csv", "a/b.csv", "a\\b.csv", ".hidden.csv", "notes.txt", "x\n.csv", "x" * 120 + ".csv"],
)
def test_bad_file_names_are_refused(client: TestClient, name: str) -> None:
    headers = new_workspace(client)
    assert upload(client, headers, name, b"id\n1\n") == 400
    assert check_file_name(" Orders (final).CSV ") == "Orders (final).CSV"


def _fill(store: WorkspaceStore, workspace_id: str) -> Path:
    """Give a workspace every kind of file Delete must remove."""
    folder = store.root / workspace_id
    for name in ("data.sqlite", "data.sqlite-wal", "data.sqlite-journal", "registry.yaml"):
        (folder / name).write_bytes(b"x")
    conn = sqlite3.connect(folder / "audit.sqlite")
    conn.execute("CREATE TABLE ask_log (question TEXT)")
    conn.execute("INSERT INTO ask_log VALUES ('how many?')")
    conn.commit()
    conn.close()
    return folder


def test_delete_removes_files_sidecars_uploads_registry_and_ask_log(
    client: TestClient, store: WorkspaceStore
) -> None:
    headers = new_workspace(client)
    upload_sample(client, headers)
    folder = _fill(store, headers[HEADER])
    assert any((folder / "uploads").iterdir())
    response = client.delete("/api/workspace", headers=headers)
    assert response.json() == {"deleted": True}
    assert not folder.exists()
    assert list((store.root / ".trash").iterdir()) == []
    assert client.get("/api/workspace", headers=headers).status_code == 404


def test_expiry_shown_and_extended_by_activity(client: TestClient, clock: FakeClock) -> None:
    headers = new_workspace(client)
    first = client.get("/api/workspace", headers=headers).json()["expires_at"]
    assert first == "2026-11-18T15:00:00+00:00"
    clock.advance(days=6)
    later = client.get("/api/workspace", headers=headers).json()["expires_at"]
    assert later == "2026-11-24T15:00:00+00:00"


def test_sweep_removes_a_workspace_idle_for_seven_days(
    store: WorkspaceStore, clock: FakeClock
) -> None:
    idle = store.create("1.1.1.1")
    busy = store.create("1.1.1.2")
    _fill(store, idle.id)
    clock.advance(days=6, hours=23)
    store.open(busy.id)
    assert store.sweep().removed == []
    clock.advance(hours=1)
    result = store.sweep()
    assert result.removed == [idle.id]
    assert not (store.root / idle.id).exists()
    assert (store.root / busy.id).exists()


def test_an_expired_workspace_is_gone_even_before_the_sweep(
    client: TestClient, clock: FakeClock
) -> None:
    headers = new_workspace(client)
    clock.advance(days=7)
    assert client.get("/api/workspace", headers=headers).status_code == 404


def test_sweep_tolerates_an_open_database(store: WorkspaceStore, clock: FakeClock) -> None:
    workspace = store.create("1.1.1.1")
    conn = sqlite3.connect(workspace.db_path)
    conn.execute("CREATE TABLE t (x)")
    conn.commit()
    clock.advance(days=8)
    try:
        assert store.sweep().removed == [workspace.id]
    finally:
        conn.close()
    assert not workspace.dir.exists()


def test_a_failed_removal_is_retried_on_the_next_sweep(
    store: WorkspaceStore, clock: FakeClock, monkeypatch: pytest.MonkeyPatch
) -> None:
    import shutil

    workspace = store.create("1.1.1.1")
    clock.advance(days=8)
    real_rmtree = shutil.rmtree

    def failing(path: object, *args: object, **kwargs: object) -> None:
        raise PermissionError("file in use")

    monkeypatch.setattr(shutil, "rmtree", failing)
    first = store.sweep()
    assert first.removed == [workspace.id]
    assert len(first.failed) == 1
    assert not workspace.dir.exists()  # already unreachable: it was moved to the trash
    monkeypatch.setattr(shutil, "rmtree", real_rmtree)
    second = store.sweep()
    assert second.failed == []
    assert list((store.root / ".trash").iterdir()) == []


def test_sweep_judges_a_folder_without_metadata_by_its_age(
    store: WorkspaceStore, clock: FakeClock
) -> None:
    import os

    orphan = store.root / ("f" * 32)
    orphan.mkdir()
    old = clock.now.timestamp() - 8 * 86400
    os.utime(orphan, (old, old))
    assert store.sweep().removed == ["f" * 32]


def test_cli_sweep(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from ledgerline.cli import app
    from ledgerline.config import get_settings

    monkeypatch.setenv("LEDGERLINE_WORKSPACE_DIR", str(tmp_path / "ws"))
    get_settings.cache_clear()
    try:
        result = CliRunner().invoke(app, ["sweep"])
    finally:
        get_settings.cache_clear()
    assert result.exit_code == 0, result.output
    assert "removed 0 expired workspace(s)" in result.output


def test_time_zone_is_validated(client: TestClient) -> None:
    bad = client.post("/api/workspaces", json={"time_zone": "../../etc/passwd"})
    assert bad.status_code == 400
    good = client.post("/api/workspaces", json={"time_zone": "Pacific/Auckland"})
    assert good.json()["time_zone"] == "Pacific/Auckland"
    assert "Pacific/Auckland" in client.get("/api/time-zones").json()


def test_responses_never_send_a_referrer(client: TestClient) -> None:
    response = client.get("/api/limits")
    assert response.headers["referrer-policy"] == "no-referrer"
    assert response.headers["cache-control"] == "no-store"
    assert response.json()["max_files"] == 10
