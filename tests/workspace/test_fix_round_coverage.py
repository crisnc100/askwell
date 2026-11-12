"""The failure paths behind the PR5 fix round: a write that fails half-way is undone,
an upload whose metadata cannot be saved leaves no file, the temp sweep skips this
process's own files, and the attempt limiter forgets old attempts."""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest

from ledgerline.workspace import store as store_module
from ledgerline.workspace.limits import Limits, RateLimiter
from ledgerline.workspace.store import STALE_TEMP_S, DiskFullError, WorkspaceStore
from tests.workspace.conftest import FakeClock


async def body(data: bytes) -> AsyncIterator[bytes]:
    await asyncio.sleep(0)
    yield data


def test_a_write_that_fails_half_way_puts_every_file_back(
    tmp_path: Path, clock: FakeClock, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = WorkspaceStore(tmp_path / "ws", Limits(), clock)
    existing = tmp_path / "existing.txt"
    existing.write_bytes(b"old")
    new = tmp_path / "new.txt"
    fresh = tmp_path / "third.txt"
    real = store_module.write_private
    calls: list[Path] = []

    def flaky(path: Path, data: bytes) -> None:
        calls.append(path)
        if path == fresh:
            raise OSError("disk went away")
        real(path, data)

    monkeypatch.setattr(store_module, "write_private", flaky)
    with pytest.raises(OSError, match="disk went away"):
        store.write_counted_together([(existing, b"newer"), (new, b"brand new"), (fresh, b"never")])
    assert existing.read_bytes() == b"old"
    assert not new.exists()
    assert not fresh.exists()
    assert store.capacity.reserved == 0


async def test_an_upload_whose_metadata_cannot_be_saved_leaves_no_file(
    tmp_path: Path, clock: FakeClock, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = WorkspaceStore(tmp_path / "ws", Limits(), clock)
    workspace_id = store.create("1.1.1.1").id

    real_save = store.save

    def refuse(workspace: Any) -> None:
        # Only the save that would list the new file is refused.
        if workspace.meta.files:
            raise DiskFullError("full")
        real_save(workspace)

    monkeypatch.setattr(store, "save", refuse)
    with pytest.raises(DiskFullError):
        await store.upload(store.open(workspace_id, touch=False), "a.csv", body(b"id\n1\n"))
    uploads = tmp_path / "ws" / workspace_id / "uploads"
    assert list(uploads.iterdir()) == []


def test_the_temp_sweep_never_removes_this_process_files(tmp_path: Path, clock: FakeClock) -> None:
    store = WorkspaceStore(tmp_path / "ws", Limits(), clock)
    workspace_id = store.create("1.1.1.1").id
    token = store._token  # pyright: ignore[reportPrivateUsage]
    mine = tmp_path / "ws" / workspace_id / "uploads" / f".incoming-{token}-1"
    mine.write_bytes(b"x")
    old = clock().timestamp() - STALE_TEMP_S - 1
    os.utime(mine, (old, old))
    assert store.remove_stale_temp() == []
    assert mine.exists()


def test_the_limiter_forgets_attempts_older_than_its_window() -> None:
    now = [0.0]
    limiter = RateLimiter(2, 60.0, clock=lambda: now[0])
    assert not limiter.full("a")
    limiter.allow("a")
    limiter.allow("a")
    assert limiter.full("a")
    now[0] = 61.0
    assert not limiter.full("a")
