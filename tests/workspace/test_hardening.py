"""Hardening before the hosted beta: the disk cap counts every byte a workspace writes,
temporary files outlive no crash uncounted, Check is rate limited, workspace files are
private to the server's account, slow uploads cannot hold reservations, and file names
stay out of request URLs."""

from __future__ import annotations

import asyncio
import contextlib
import os
import stat
import threading
from collections.abc import AsyncIterator
from pathlib import Path
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient

from ledgerline.api import create_app
from ledgerline.workspace import fields
from ledgerline.workspace.api import FILE_HEADER, TooManyRequestsError, WorkspaceApp
from ledgerline.workspace.ask import workspace_target
from ledgerline.workspace.check import TablePlan
from ledgerline.workspace.fields import Edits
from ledgerline.workspace.limits import Limits
from ledgerline.workspace.store import (
    LOAD_MIN_BYTES,
    STALE_TEMP_S,
    DiskFullError,
    UploadTooSlowError,
    WorkspaceStore,
)
from tests.workspace.conftest import FakeClock, _NoService, new_workspace, sample_files


async def body(data: bytes) -> AsyncIterator[bytes]:
    await asyncio.sleep(0)
    yield data


def _uploaded(store: WorkspaceStore, files: list[tuple[str, bytes]]) -> str:
    workspace_id = store.create("1.1.1.1").id

    async def go() -> None:
        for name, data in files:
            await store.upload(store.open(workspace_id), name, body(data))

    asyncio.run(go())
    return workspace_id


def _store(root: Path, clock: FakeClock, cap: int, **limits: float) -> WorkspaceStore:
    return WorkspaceStore(root, Limits(disk_cap_bytes=cap, **limits), clock)  # type: ignore[arg-type]


SMALL = [("items.csv", b"id,label\n1,a\n2,b\n")]


# --- disk cap ---


def test_check_counts_its_report_and_metadata(tmp_path: Path, clock: FakeClock) -> None:
    """For every cap near what one Check needs, the Check either fits or is refused;
    it never leaves the disk over the cap."""
    probe = _store(tmp_path / "probe", clock, 10_000_000)
    probe_id = _uploaded(probe, SMALL)
    before = probe.disk_usage()
    assert probe.check(probe.open(probe_id), after_load=fields.draft).ok
    needed = probe.disk_usage() - before

    for slack in range(-400, 1, 25):
        store = _store(tmp_path / f"cap{slack + 400}", clock, 10_000_000)
        workspace_id = _uploaded(store, SMALL)
        store.capacity.cap = store.disk_usage() + needed + slack
        with contextlib.suppress(DiskFullError):
            store.check(store.open(workspace_id), after_load=fields.draft)
        assert store.disk_usage() <= store.capacity.cap, slack
        assert store.capacity.reserved == 0


def test_two_checks_cannot_grow_into_the_same_free_space(tmp_path: Path, clock: FakeClock) -> None:
    """Both Checks finish building before either swaps its files in. Only one may
    claim the space that fits one."""
    store = _store(tmp_path / "ws", clock, 10_000_000)
    first = _uploaded(store, SMALL)
    second = _uploaded(store, SMALL)
    probe = _store(tmp_path / "probe", clock, 10_000_000)
    probe_id = _uploaded(probe, SMALL)
    before = probe.disk_usage()
    assert probe.check(probe.open(probe_id), after_load=fields.draft).ok
    built = probe.disk_usage() - before
    # What each Check reserves before it builds: the minimum load estimate (the CSV is
    # tiny) plus its report. The database it builds is larger than that.
    reserved_first = LOAD_MIN_BYTES + probe.open(probe_id).check_path.stat().st_size
    assert built > reserved_first
    # Room for both first reservations and for one finished Check, not for two.
    store.capacity.cap = store.disk_usage() + reserved_first + built + (built - reserved_first) // 2

    barrier = threading.Barrier(2, timeout=10)

    def draft_then_wait(path: Path, tables: list[TablePlan]) -> dict[str, str]:
        out = fields.draft(path, tables)
        barrier.wait()
        return out

    outcomes: list[str] = []

    def run(workspace_id: str) -> None:
        try:
            store.check(store.open(workspace_id), after_load=draft_then_wait)
            outcomes.append("ok")
        except DiskFullError:
            outcomes.append("full")

    threads = [threading.Thread(target=run, args=(w,)) for w in (first, second)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert sorted(outcomes) == ["full", "ok"]
    assert store.disk_usage() <= store.capacity.cap
    assert store.capacity.reserved == 0


def _foreign_temp(store: WorkspaceStore, workspace_id: str, size: int) -> Path:
    """A temporary upload file left by another process (a different token)."""
    path = store.root / workspace_id / "uploads" / ".incoming-0badc0de-1234"
    path.write_bytes(b"x" * size)
    return path


def test_another_process_temp_files_are_counted(tmp_path: Path, clock: FakeClock) -> None:
    store = _store(tmp_path / "ws", clock, 10_000_000)
    workspace_id = _uploaded(store, SMALL)
    before = store.disk_usage()
    leftover = _foreign_temp(store, workspace_id, 5000)
    os.utime(leftover, (clock().timestamp(), clock().timestamp()))
    restarted = _store(tmp_path / "ws", clock, 10_000_000)
    assert leftover.exists()  # too young to be stale
    assert restarted.disk_usage() == before + 5000


def test_a_restart_removes_stale_temp_files(tmp_path: Path, clock: FakeClock) -> None:
    store = _store(tmp_path / "ws", clock, 10_000_000)
    workspace_id = _uploaded(store, SMALL)
    leftover = _foreign_temp(store, workspace_id, 5000)
    staging = store.root / workspace_id / ".staging-0badc0de-99"
    staging.mkdir()
    (staging / "data.sqlite").write_bytes(b"y" * 3000)
    old = clock().timestamp() - STALE_TEMP_S - 1
    for path in (leftover, staging):
        os.utime(path, (old, old))

    restarted = _store(tmp_path / "ws", clock, 10_000_000)

    assert not leftover.exists()
    assert not staging.exists()
    assert restarted.disk_usage() < 5000 + 3000 + store.disk_usage()


def test_the_sweep_also_removes_stale_temp_files(tmp_path: Path, clock: FakeClock) -> None:
    store = _store(tmp_path / "ws", clock, 10_000_000)
    workspace_id = _uploaded(store, SMALL)
    leftover = _foreign_temp(store, workspace_id, 10)
    clock.advance(seconds=STALE_TEMP_S + 1)
    old = clock().timestamp() - STALE_TEMP_S - 1
    os.utime(leftover, (old, old))
    store.sweep()
    assert not leftover.exists()


# --- rate limit on Check ---


def test_check_is_rate_limited_per_address(tmp_path: Path, clock: FakeClock) -> None:
    store = _store(tmp_path / "ws", clock, 10_000_000, checks_per_hour=2)
    app = create_app(service=_NoService(), workspaces=WorkspaceApp(store))  # type: ignore[arg-type]
    with TestClient(app) as client:
        headers = new_workspace(client)
        put = {**headers, FILE_HEADER: "items.csv"}
        assert client.put("/api/workspace/files", content=SMALL[0][1], headers=put).is_success
        for _ in range(2):
            assert client.post("/api/workspace/check", headers=headers).status_code == 200
        refused = client.post("/api/workspace/check", headers=headers)
    assert refused.status_code == 429
    assert "checks" in refused.json()["detail"]


# --- permissions ---


def _mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


async def test_workspace_folders_and_files_are_private(store: WorkspaceStore) -> None:
    os.chmod(store.root, 0o755)  # noqa: S103 - a root left open by an older version
    store = WorkspaceStore(store.root, store.limits, store.clock)
    workspace_id = store.create("1.1.1.1").id
    for item in sample_files():
        await store.upload(store.open(workspace_id), item.name, body(item.data))
    assert store.check(store.open(workspace_id), after_load=fields.draft).ok
    fields.confirm(store, store.open(workspace_id), Edits())
    workspace = store.open(workspace_id)
    with workspace_target(workspace, store.clock):
        pass

    folders = [store.root, workspace.dir, workspace.uploads]
    for folder in folders:
        assert _mode(folder) == 0o700, folder
    files = [p for p in workspace.dir.rglob("*") if p.is_file()]
    names = {p.name for p in files}
    for expected in ("meta.json", "data.sqlite", "check.json", "registry.yaml", "audit.sqlite"):
        assert expected in names
    assert any(p.parent == workspace.uploads for p in files)
    for path in files:
        assert _mode(path) == 0o600, path


# --- slow uploads ---


async def test_an_upload_past_its_time_limit_is_refused_and_frees_its_space(
    tmp_path: Path, clock: FakeClock
) -> None:
    store = _store(tmp_path / "ws", clock, 10_000_000, upload_seconds=0.05)
    workspace_id = store.create("1.1.1.1").id
    never = asyncio.Event()

    async def stalled() -> AsyncIterator[bytes]:
        yield b"id\n"
        await never.wait()
        yield b"1\n"

    with pytest.raises(UploadTooSlowError):
        await store.upload(store.open(workspace_id), "slow.csv", stalled(), 1_000_000)
    assert store.capacity.reserved == 0
    uploads = store.open(workspace_id).uploads
    assert list(uploads.iterdir()) == []


def test_one_address_may_run_only_a_few_uploads_at_once(store: WorkspaceStore) -> None:
    app = WorkspaceApp(store)
    limit = store.limits.uploads_in_flight_per_ip
    with app.upload_slot("1.1.1.1"), app.upload_slot("1.1.1.1"):
        assert limit == 2
        with pytest.raises(TooManyRequestsError), app.upload_slot("1.1.1.1"):
            pass
        with app.upload_slot("2.2.2.2"):
            pass
    with app.upload_slot("1.1.1.1"):
        pass


# --- file names stay out of URLs ---


def test_a_file_name_travels_in_a_header(client: TestClient) -> None:
    headers = new_workspace(client)
    name = "Q3 résumé, final.csv"
    put = client.put(
        "/api/workspace/files",
        content=SMALL[0][1],
        headers={**headers, FILE_HEADER: quote(name)},
    )
    assert put.status_code == 200, put.text
    assert [f["name"] for f in put.json()["files"]] == [name]
    assert name not in str(put.request.url)
    removed = client.delete("/api/workspace/files", headers={**headers, FILE_HEADER: quote(name)})
    assert removed.status_code == 200
    assert removed.json()["files"] == []


def test_a_file_name_that_is_not_utf8_is_a_plain_refusal(client: TestClient) -> None:
    headers = new_workspace(client)
    put = client.put(
        "/api/workspace/files", content=b"id\n1\n", headers={**headers, FILE_HEADER: "%ff.csv"}
    )
    assert put.status_code == 400
    assert "percent-encoded" in put.json()["detail"]
