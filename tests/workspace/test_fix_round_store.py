"""PR5 review fixes on workspaces: a refused re-confirm changes nothing, an upload that
times out mid-reservation leaks nothing, a same-size rewrite never fails on a full disk,
and a refused create leaves no folder behind."""

from __future__ import annotations

import asyncio
import threading
import time
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest

from askwell.workspace import fields
from askwell.workspace.fields import Edits
from askwell.workspace.limits import Limits
from askwell.workspace.store import DiskFullError, UploadTooSlowError, WorkspaceStore
from tests.workspace.conftest import FakeClock, sample_files


async def body(data: bytes) -> AsyncIterator[bytes]:
    await asyncio.sleep(0)
    yield data


async def _confirmed(store: WorkspaceStore) -> str:
    workspace_id = store.create("1.1.1.1").id
    for item in sample_files():
        await store.upload(store.open(workspace_id), item.name, body(item.data))
    assert store.check(store.open(workspace_id), after_load=fields.draft).ok
    fields.confirm(store, store.open(workspace_id), Edits())
    return workspace_id


def _edits(store: WorkspaceStore, workspace_id: str) -> Edits:
    """Edits that grow both registry.yaml and edits.json: a long description per field."""
    registry, _ = fields.load_draft(store.open(workspace_id))
    entity = next(iter(registry.entities))
    name = next(iter(registry.entities[entity].fields))
    return Edits.model_validate(
        {"fields": {f"{entity}.{name}": {"description": "A field described at length. " * 9}}}
    )


async def test_a_refused_reconfirm_leaves_the_registry_and_edits_as_they_were(
    tmp_path: Path, clock: FakeClock
) -> None:
    probe = WorkspaceStore(tmp_path / "probe", Limits(), clock)
    probe_id = await _confirmed(probe)
    before = probe.disk_usage()
    fields.confirm(probe, probe.open(probe_id), _edits(probe, probe_id))
    growth = probe.disk_usage() - before
    assert growth > 2

    store = WorkspaceStore(tmp_path / "ws", Limits(), clock)
    workspace_id = await _confirmed(store)
    workspace = store.open(workspace_id)
    registry_before = workspace.registry_path.read_bytes()
    edits_before = workspace.edits_path.read_bytes()
    store.capacity.cap = store.disk_usage() + growth - 1

    with pytest.raises(DiskFullError):
        fields.confirm(store, store.open(workspace_id), _edits(store, workspace_id))

    workspace = store.open(workspace_id)
    assert workspace.registry_path.read_bytes() == registry_before
    assert workspace.edits_path.read_bytes() == edits_before
    assert workspace.meta.state == "confirmed"
    assert store.capacity.reserved == 0


async def test_a_timeout_during_a_reservation_leaks_nothing(
    tmp_path: Path, clock: FakeClock, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = WorkspaceStore(tmp_path / "ws", Limits(upload_seconds=0.05), clock)
    workspace_id = store.create("1.1.1.1").id
    real = store._reserve_more  # pyright: ignore[reportPrivateUsage]
    done = threading.Event()

    def slow(*args: Any, **kwargs: Any) -> Any:
        time.sleep(0.2)  # the deadline passes while this runs in its thread
        try:
            return real(*args, **kwargs)
        finally:
            done.set()

    monkeypatch.setattr(store, "_reserve_more", slow)
    with pytest.raises(UploadTooSlowError):
        await store.upload(store.open(workspace_id), "a.csv", body(b"id\n1\n"))
    assert done.wait(5)
    await asyncio.sleep(0.05)
    assert store.capacity.reserved == 0


async def test_a_visit_rewrites_metadata_even_over_the_cap(
    tmp_path: Path, clock: FakeClock
) -> None:
    store = WorkspaceStore(tmp_path / "ws", Limits(), clock)
    workspace_id = store.create("1.1.1.1").id
    store.capacity.cap = store.disk_usage() - 1  # usage already past the cap
    clock.advance(minutes=1)
    workspace = store.open(workspace_id)  # a visit touches last_activity: same size
    assert workspace.meta.id == workspace_id


def test_a_refused_create_leaves_no_folder(tmp_path: Path, clock: FakeClock) -> None:
    store = WorkspaceStore(tmp_path / "ws", Limits(), clock)
    store.owner_tag("1.1.1.1")  # the address key exists before the refused create
    store.capacity.cap = store.disk_usage()  # no room for a meta.json
    before = sorted(p.name for p in store.root.iterdir())
    with pytest.raises(DiskFullError):
        store.create("1.1.1.1")
    assert sorted(p.name for p in store.root.iterdir()) == before
