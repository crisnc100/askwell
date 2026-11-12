"""Workspace changes that overlap, and the disk cap under concurrent use.

Every change to a workspace re-reads its metadata under that workspace's lock, so two
requests never overwrite each other's files or state. Disk space is reserved before it
is written, so two uploads cannot both spend the same free space, and a load reserves
room for the database it builds (larger than the CSV files) before it replaces anything.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from ledgerline.workspace import fields
from ledgerline.workspace.fields import Edits
from ledgerline.workspace.limits import Limits
from ledgerline.workspace.store import (
    DiskFullError,
    WorkspaceNotFoundError,
    WorkspaceStore,
    WrongStateError,
)
from tests.workspace.conftest import FakeClock, sample_files


async def body(data: bytes, pieces: int = 10) -> AsyncIterator[bytes]:
    """`data` in `pieces` chunks, yielding to the event loop between them."""
    step = max(1, -(-len(data) // pieces))
    for start in range(0, len(data), step):
        await asyncio.sleep(0)
        yield data[start : start + step]


async def checked_store(store: WorkspaceStore) -> str:
    workspace = store.create("1.1.1.1")
    for item in sample_files():
        await store.upload(store.open(workspace.id), item.name, body(item.data))
    assert store.check(store.open(workspace.id), after_load=fields.draft).ok
    return workspace.id


def _fill_to(store: WorkspaceStore, free: int) -> None:
    """Add a filler file so exactly `free` bytes remain under the cap."""
    filler = store.root / "filler"
    filler.unlink(missing_ok=True)
    size = store.limits.disk_cap_bytes - store.disk_usage() - free
    assert size >= 0
    filler.write_bytes(b"x" * size)


async def test_two_overlapping_uploads_keep_both_files(store: WorkspaceStore) -> None:
    workspace_id = store.create("1.1.1.1").id
    first, second = store.open(workspace_id), store.open(workspace_id)
    await asyncio.gather(
        store.upload(first, "a.csv", body(b"id\n1\n" * 20)),
        store.upload(second, "b.csv", body(b"id\n2\n" * 20)),
    )
    meta = store.open(workspace_id).meta
    assert sorted(f.name for f in meta.files) == ["a.csv", "b.csv"]
    assert len({f.stored for f in meta.files}) == 2
    uploads = store.open(workspace_id).uploads
    for entry in meta.files:
        assert (uploads / entry.stored).exists()


async def test_an_upload_finishing_after_confirm_is_refused(store: WorkspaceStore) -> None:
    workspace_id = await checked_store(store)
    stale = store.open(workspace_id)
    gate = asyncio.Event()

    async def slow() -> AsyncIterator[bytes]:
        yield b"id\n"
        await gate.wait()
        yield b"1\n"

    task = asyncio.create_task(store.upload(stale, "late.csv", slow()))
    await asyncio.sleep(0.05)
    fields.confirm(store, store.open(workspace_id), Edits())
    gate.set()
    with pytest.raises(WrongStateError):
        await task
    meta = store.open(workspace_id).meta
    assert meta.state == "confirmed"
    assert "late.csv" not in [f.name for f in meta.files]


async def test_an_upload_finishing_after_delete_does_not_bring_it_back(
    store: WorkspaceStore,
) -> None:
    workspace_id = store.create("1.1.1.1").id
    stale = store.open(workspace_id)
    gate = asyncio.Event()

    async def slow() -> AsyncIterator[bytes]:
        yield b"id\n"
        await gate.wait()
        yield b"1\n"

    task = asyncio.create_task(store.upload(stale, "late.csv", slow()))
    await asyncio.sleep(0.05)
    assert store.delete(workspace_id)
    gate.set()
    with pytest.raises(WorkspaceNotFoundError):
        await task
    assert not (store.root / workspace_id).exists()


async def test_two_uploads_cannot_spend_the_same_free_space(
    tmp_path: Path, clock: FakeClock
) -> None:
    """With a declared size (a browser always sends one for a file), the first upload
    reserves its whole size, so exactly one of two fits."""
    store = WorkspaceStore(tmp_path / "ws", Limits(disk_cap_bytes=50_000), clock)
    workspace_id = store.create("1.1.1.1").id
    _fill_to(store, 1500)
    results = await asyncio.gather(
        store.upload(store.open(workspace_id), "a.csv", body(b"x" * 1000), 1000),
        store.upload(store.open(workspace_id), "b.csv", body(b"y" * 1000), 1000),
        return_exceptions=True,
    )
    assert sum(isinstance(r, DiskFullError) for r in results) == 1
    assert store.disk_usage() <= store.limits.disk_cap_bytes
    # The refused upload gave its reservation back: what is left can still be used.
    _fill_to(store, 600)
    await store.upload(store.open(workspace_id), "c.csv", body(b"z" * 300))


async def test_uploads_without_a_declared_size_never_overspend(
    tmp_path: Path, clock: FakeClock
) -> None:
    """Without a declared size, room is reserved as bytes arrive: two uploads racing for
    the same space may both be refused, but never both stored."""
    store = WorkspaceStore(tmp_path / "ws", Limits(disk_cap_bytes=50_000), clock)
    workspace_id = store.create("1.1.1.1").id
    _fill_to(store, 1500)
    results = await asyncio.gather(
        store.upload(store.open(workspace_id), "a.csv", body(b"x" * 1000)),
        store.upload(store.open(workspace_id), "b.csv", body(b"y" * 1000)),
        return_exceptions=True,
    )
    assert sum(isinstance(r, DiskFullError) for r in results) >= 1
    assert store.disk_usage() <= store.limits.disk_cap_bytes
    assert store.capacity.reserved == 0


async def test_a_refused_recheck_keeps_the_loaded_workspace(
    tmp_path: Path, clock: FakeClock
) -> None:
    store = WorkspaceStore(tmp_path / "ws", Limits(disk_cap_bytes=2_000_000), clock)
    workspace_id = await checked_store(store)
    _fill_to(store, 100)
    with pytest.raises(DiskFullError):
        store.check(store.open(workspace_id), after_load=fields.draft)
    workspace = store.open(workspace_id)
    assert workspace.meta.state == "checked"
    for path in (workspace.db_path, workspace.draft_path, workspace.fields_path):
        assert path.exists(), path
    assert workspace.check_path.exists()
    assert store.disk_usage() <= store.limits.disk_cap_bytes


async def test_a_load_reserves_room_for_the_database_not_just_the_csv(
    tmp_path: Path, clock: FakeClock
) -> None:
    store = WorkspaceStore(tmp_path / "ws", Limits(disk_cap_bytes=60_000), clock)
    workspace_id = store.create("1.1.1.1").id
    await store.upload(store.open(workspace_id), "items.csv", body(b"id\n1\n"))
    _fill_to(store, 2000)  # room for the 5-byte CSV, not for an 8 KiB database
    with pytest.raises(DiskFullError):
        store.check(store.open(workspace_id), after_load=fields.draft)
    workspace = store.open(workspace_id)
    assert workspace.meta.state == "new"
    assert not workspace.db_path.exists()
    assert store.disk_usage() <= store.limits.disk_cap_bytes
    assert [p.name for p in workspace.dir.iterdir() if p.name.startswith(".")] == []
