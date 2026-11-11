"""Workspaces on disk: one private folder per workspace, and its lifecycle.

A workspace moves `new -> checked -> confirmed`:
- `new`: files can be uploaded. A file with the same name replaces the old one, and any
  upload (or removal) moves the workspace back to `new`.
- `checked`: every file passed Check and the set is loaded into the workspace's SQLite
  file. Uploading is still allowed (and goes back to `new`).
- `confirmed`: the person confirmed what the model may see. Uploading is refused; a
  changed data set starts a new workspace.

Everything a workspace holds lives in its folder: the raw uploads, the SQLite file and
its `-wal`/`-journal` sidecars, the registry, the shared category values and its own
`ask_log`. Deleting the folder deletes all of it.

The workspace id is a bearer secret: 128 random bits from `secrets`, as 32 hex
characters. Anything else is refused before a path is built from it. It expires
`Limits.idle_days` after its last use.

Requests can overlap. Every change to a workspace runs inside `locked`, which holds that
workspace's lock, reads its metadata fresh from disk and saves it before letting go, so
no request acts on a stale copy. Disk space is reserved before it is written
(`Capacity`), so two requests can never both spend the same free space. Files still
being written (an upload streaming in, a load being built) are covered by their
reservation, not counted twice.
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import hmac
import json
import os
import re
import secrets
import shutil
import threading
from collections.abc import AsyncIterator, Callable, Generator
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Literal
from zoneinfo import available_timezones

from ledgerline.workspace.check import CheckResult, TablePlan, UploadedFile, check_files
from ledgerline.workspace.limits import MB, Limits
from ledgerline.workspace.load import load_tables

State = Literal["new", "checked", "confirmed"]
DEFAULT_TIME_ZONE = "America/New_York"
WORKSPACE_ID = re.compile(r"[0-9a-f]{32}")
_TRASH = ".trash"
_INCOMING = ".incoming-"
_STAGING = ".staging-"
DRAFT_FILE = "registry.draft.yaml"
FIELDS_FILE = "fields.json"
# A load reserves this much before building, then checks the real size before swapping
# it in: a SQLite file is larger than its CSV (a 5-byte CSV makes an 8 KiB database).
LOAD_MIN_BYTES = 8 * 1024
LOAD_FACTOR = 3
# Uploads without a declared size reserve room in steps of this size (exactly what is
# needed when less than a step is left).
RESERVE_STEP = 256 * 1024
_OWNER_KEY_FILE = ".owner-key"
MAX_NAME_CHARS = 100
_CSV_NAME = re.compile(r".+\.csv", re.IGNORECASE)


class WorkspaceError(Exception):
    """A refusal the person can act on. `status` is the HTTP status the API returns."""

    status = 400

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class InvalidWorkspaceIdError(WorkspaceError):
    status = 400


class WorkspaceNotFoundError(WorkspaceError):
    status = 404


class WrongStateError(WorkspaceError):
    status = 409


class FileTooLargeError(WorkspaceError):
    status = 413


class LimitReachedError(WorkspaceError):
    status = 429


class DiskFullError(WorkspaceError):
    status = 507


NOT_FOUND = "No workspace has that link. It may have expired or been deleted."
CONFIRMED = (
    "This workspace is confirmed, so its files are fixed. Start a new workspace to use "
    "different files."
)
DISK_FULL = "The service is out of space right now. Try again later."


@dataclass
class FileEntry:
    name: str
    stored: str
    bytes: int
    uploaded_at: str


@dataclass
class Meta:
    id: str
    state: State
    created_at: str
    last_activity: str
    time_zone: str
    owner: str
    files: list[FileEntry] = field(default_factory=list[FileEntry])
    next_file: int = 1

    @classmethod
    def from_json(cls, text: str) -> Meta:
        data = json.loads(text)
        data["files"] = [FileEntry(**f) for f in data.get("files", [])]
        return cls(**data)

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2)


def parse_workspace_id(raw: str | None) -> str:
    """The id if it is exactly 32 lowercase hex characters; refused otherwise, before
    any file is touched."""
    if raw is None or not WORKSPACE_ID.fullmatch(raw):
        raise InvalidWorkspaceIdError("That is not a workspace link.")
    return raw


@lru_cache(maxsize=1)
def time_zones() -> frozenset[str]:
    return frozenset(available_timezones())


def check_file_name(name: str) -> str:
    """A file name as uploaded: a `.csv` name with no path or control characters."""
    name = name.strip()
    if (
        not _CSV_NAME.fullmatch(name)
        or len(name) > MAX_NAME_CHARS
        or name.startswith(".")
        or any(c in name for c in "/\\")
        or any(ord(c) < 32 for c in name)
    ):
        raise WorkspaceError(
            f"Upload CSV files with a plain name ending in .csv (at most {MAX_NAME_CHARS} "
            "characters, no slashes)."
        )
    return name


class Workspace:
    """One workspace's folder and metadata."""

    def __init__(self, root: Path, meta: Meta) -> None:
        self.dir = root / meta.id
        self.meta = meta

    @property
    def id(self) -> str:
        return self.meta.id

    @property
    def uploads(self) -> Path:
        return self.dir / "uploads"

    @property
    def db_path(self) -> Path:
        return self.dir / "data.sqlite"

    @property
    def registry_path(self) -> Path:
        return self.dir / "registry.yaml"

    @property
    def draft_path(self) -> Path:
        return self.dir / DRAFT_FILE

    @property
    def fields_path(self) -> Path:
        return self.dir / FIELDS_FILE

    @property
    def edits_path(self) -> Path:
        return self.dir / "edits.json"

    @property
    def audit_path(self) -> Path:
        return self.dir / "audit.sqlite"

    @property
    def check_path(self) -> Path:
        return self.dir / "check.json"

    def save(self) -> None:
        tmp = self.dir / "meta.json.tmp"
        tmp.write_text(self.meta.to_json(), encoding="utf-8")
        os.replace(tmp, self.dir / "meta.json")

    def clear_loaded(self) -> None:
        """Remove everything built from the uploads (back to `new`)."""
        for path in (
            self.registry_path,
            self.draft_path,
            self.fields_path,
            self.edits_path,
            self.check_path,
        ):
            path.unlink(missing_ok=True)
        for suffix in ("", "-wal", "-journal", "-shm"):
            self.db_path.with_name(self.db_path.name + suffix).unlink(missing_ok=True)

    def read_files(self) -> list[UploadedFile]:
        return [
            UploadedFile(f.name, (self.uploads / f.stored).read_bytes()) for f in self.meta.files
        ]


class Capacity:
    """The disk cap shared by all workspaces. Space is reserved under one lock before it
    is written and released once the bytes are on disk (or abandoned)."""

    def __init__(self, cap: int, usage: Callable[[], int]) -> None:
        self.cap = cap
        self.usage = usage
        self.reserved = 0
        self._lock = threading.Lock()

    def reserve(self, size: int) -> None:
        with self._lock:
            if self.usage() + self.reserved + size > self.cap:
                raise DiskFullError(DISK_FULL)
            self.reserved += size

    def release(self, size: int) -> None:
        with self._lock:
            self.reserved -= size

    def fits(self, size: int, held: int) -> bool:
        """Whether `size` more bytes fit, for a caller already holding `held` of the
        reserved total."""
        with self._lock:
            return self.usage() + self.reserved - held + size <= self.cap


@dataclass
class SweepResult:
    removed: list[str] = field(default_factory=list[str])
    failed: list[str] = field(default_factory=list[str])


class WorkspaceStore:
    def __init__(
        self,
        root: Path,
        limits: Limits | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.root = root
        self.limits = limits or Limits()
        self.clock = clock
        self._locks: dict[str, threading.RLock] = {}
        self._locks_guard = threading.Lock()
        self.capacity = Capacity(self.limits.disk_cap_bytes, self.disk_usage)
        root.mkdir(parents=True, exist_ok=True)

    def lock(self, workspace_id: str) -> threading.RLock:
        with self._locks_guard:
            return self._locks.setdefault(workspace_id, threading.RLock())

    @contextmanager
    def locked(self, workspace_id: str) -> Generator[Workspace]:
        """The workspace, read fresh under its lock; saved on a normal exit. An exception
        leaves the metadata on disk as it was."""
        with self.lock(workspace_id):
            meta = self._read_meta(workspace_id)
            if meta is None:
                raise WorkspaceNotFoundError(NOT_FOUND)
            workspace = Workspace(self.root, meta)
            yield workspace
            workspace.save()

    def _now(self) -> datetime:
        return self.clock().astimezone(UTC)

    def owner_tag(self, ip: str) -> str:
        """A keyed hash of the client IP: enough to count one IP's workspaces, without
        storing the IP. The key is random per data folder."""
        path = self.root / _OWNER_KEY_FILE
        if not path.exists():
            with contextlib.suppress(FileExistsError):
                fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(fd, "wb") as fh:
                    fh.write(secrets.token_bytes(32))
        key = path.read_bytes()
        return hmac.new(key, ip.encode(), hashlib.sha256).hexdigest()[:32]

    def expires_at(self, meta: Meta) -> datetime:
        return datetime.fromisoformat(meta.last_activity) + timedelta(days=self.limits.idle_days)

    def _expired(self, meta: Meta) -> bool:
        return self.expires_at(meta) <= self._now()

    def _read_meta(self, workspace_id: str) -> Meta | None:
        path = self.root / workspace_id / "meta.json"
        try:
            return Meta.from_json(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError, KeyError):
            return None

    def live(self) -> list[Meta]:
        out: list[Meta] = []
        for entry in sorted(self.root.iterdir()):
            if not WORKSPACE_ID.fullmatch(entry.name):
                continue
            meta = self._read_meta(entry.name)
            if meta is not None and not self._expired(meta):
                out.append(meta)
        return out

    def create(self, ip: str, time_zone: str = DEFAULT_TIME_ZONE) -> Workspace:
        if time_zone not in time_zones():
            raise WorkspaceError("Pick a time zone from the list.")
        owner = self.owner_tag(ip)
        with self._locks_guard:
            mine = [m for m in self.live() if m.owner == owner]
            if len(mine) >= self.limits.workspaces_per_ip:
                raise LimitReachedError(
                    f"You already have {len(mine)} workspaces. Delete one, or wait for one "
                    "to expire."
                )
            workspace_id = secrets.token_hex(16)
            now = self._now().isoformat()
            meta = Meta(workspace_id, "new", now, now, time_zone, owner)
            workspace = Workspace(self.root, meta)
            workspace.dir.mkdir()
            workspace.uploads.mkdir()
            workspace.save()
        return workspace

    def open(self, raw_id: str | None, *, touch: bool = True) -> Workspace:
        """The workspace for `raw_id`, after checking the id's form. An expired one is
        deleted and reported as not found. Opening counts as activity."""
        workspace_id = parse_workspace_id(raw_id)
        meta = self._read_meta(workspace_id)
        if meta is None:
            raise WorkspaceNotFoundError(NOT_FOUND)
        if self._expired(meta):
            self.delete(workspace_id)
            raise WorkspaceNotFoundError(NOT_FOUND)
        if not touch:
            return Workspace(self.root, meta)
        with self.locked(workspace_id) as workspace:
            workspace.meta.last_activity = self._now().isoformat()
        return workspace

    def delete(self, workspace_id: str) -> bool:
        """Remove the workspace's folder. It is first renamed into the trash, so it is
        gone for every reader at once; if removing the trash copy fails, `sweep` tries
        again. Returns False when nothing was there."""
        workspace_id = parse_workspace_id(workspace_id)
        source = self.root / workspace_id
        trash = self.root / _TRASH
        trash.mkdir(exist_ok=True)
        target = trash / f"{workspace_id}-{secrets.token_hex(4)}"
        with self.lock(workspace_id):
            try:
                os.replace(source, target)
            except FileNotFoundError:
                return False
        with contextlib.suppress(OSError):
            shutil.rmtree(target)
        return True

    def sweep(self) -> SweepResult:
        """Delete every expired workspace and empty the trash. Safe to run from cron at
        any time; anything it cannot remove now is retried on the next run."""
        result = SweepResult()
        for entry in sorted(self.root.iterdir()):
            if not WORKSPACE_ID.fullmatch(entry.name):
                continue
            meta = self._read_meta(entry.name)
            if meta is None:
                # No readable metadata: judge by the folder's age.
                stamp = datetime.fromtimestamp(entry.stat().st_mtime, UTC)
                expired = stamp + timedelta(days=self.limits.idle_days) <= self._now()
            else:
                expired = self._expired(meta)
            if expired:
                try:
                    self.delete(entry.name)
                    result.removed.append(entry.name)
                except OSError:
                    result.failed.append(entry.name)
        trash = self.root / _TRASH
        if trash.exists():
            for entry in sorted(trash.iterdir()):
                try:
                    shutil.rmtree(entry)
                except OSError:
                    result.failed.append(entry.name)
        return result

    def disk_usage(self) -> int:
        """Bytes on disk under the root, leaving out files still being written: their
        reservations already count them."""
        total = 0
        for dirpath, dirs, files in os.walk(self.root):
            dirs[:] = [d for d in dirs if not d.startswith(_STAGING)]
            for name in files:
                if name.startswith(_INCOMING):
                    continue
                with contextlib.suppress(OSError):
                    total += (Path(dirpath) / name).stat().st_size
        return total

    async def upload(
        self,
        workspace: Workspace,
        name: str,
        chunks: AsyncIterator[bytes],
        content_length: int | None = None,
    ) -> FileEntry:
        """Store one uploaded file while it streams in, refusing it as soon as it passes
        the per-file size limit or the disk cap. The locked steps run in a worker
        thread, so a busy workspace never blocks the event loop."""
        name = check_file_name(name)
        await asyncio.to_thread(self._may_upload, workspace.id, name)
        limit = self.limits.max_file_bytes
        if content_length is not None and content_length > limit:
            raise FileTooLargeError(_too_large(limit))
        incoming = workspace.uploads / f"{_INCOMING}{secrets.token_hex(8)}"
        received = 0
        reserved = 0
        try:
            if content_length:
                await asyncio.to_thread(self.capacity.reserve, content_length)
                reserved = content_length
            with incoming.open("wb") as fh:
                async for chunk in chunks:
                    received += len(chunk)
                    if received > limit:
                        raise FileTooLargeError(_too_large(limit))
                    if received > reserved:
                        reserved += await asyncio.to_thread(
                            self._reserve_more, received - reserved, limit - reserved
                        )
                    fh.write(chunk)
            return await asyncio.to_thread(
                self._commit_upload, workspace.id, name, incoming, received
            )
        finally:
            incoming.unlink(missing_ok=True)
            self.capacity.release(reserved)

    def _reserve_more(self, needed: int, most: int) -> int:
        """Reserve a step ahead when there is room, or exactly what is needed."""
        step = min(max(needed, RESERVE_STEP), most)
        try:
            self.capacity.reserve(step)
        except DiskFullError:
            if step == needed:
                raise
            self.capacity.reserve(needed)
            return needed
        return step

    def _may_upload(self, workspace_id: str, name: str) -> None:
        """Refuse early what the commit would refuse anyway."""
        with self.locked(workspace_id) as workspace:
            self._check_room_for(workspace.meta, name)

    def _check_room_for(self, meta: Meta, name: str) -> FileEntry | None:
        if meta.state == "confirmed":
            raise WrongStateError(CONFIRMED)
        replacing = next((f for f in meta.files if f.name == name), None)
        if replacing is None and len(meta.files) >= self.limits.max_files:
            raise WrongStateError(
                f"A workspace holds at most {self.limits.max_files} files. Remove one first."
            )
        return replacing

    def _commit_upload(
        self, workspace_id: str, name: str, incoming: Path, received: int
    ) -> FileEntry:
        with self.locked(workspace_id) as workspace:
            meta = workspace.meta
            replacing = self._check_room_for(meta, name)
            stored = f"f{meta.next_file}.csv"
            meta.next_file += 1
            os.replace(incoming, workspace.uploads / stored)
            if replacing is not None:
                (workspace.uploads / replacing.stored).unlink(missing_ok=True)
                meta.files.remove(replacing)
            entry = FileEntry(name, stored, received, self._now().isoformat())
            meta.files.append(entry)
            meta.state = "new"
            workspace.clear_loaded()
        return entry

    def remove_file(self, workspace: Workspace, name: str) -> None:
        with self.locked(workspace.id) as fresh:
            meta = fresh.meta
            if meta.state == "confirmed":
                raise WrongStateError(CONFIRMED)
            entry = next((f for f in meta.files if f.name == name), None)
            if entry is None:
                raise WorkspaceNotFoundError(f"No file named {name!r} in this workspace.")
            (fresh.uploads / entry.stored).unlink(missing_ok=True)
            meta.files.remove(entry)
            meta.state = "new"
            fresh.clear_loaded()

    def check(
        self,
        workspace: Workspace,
        after_load: Callable[[Path, list[TablePlan]], dict[str, str]] | None = None,
    ) -> CheckResult:
        """Check every file. If the whole set passes, build the database (and the files
        `after_load` returns for it, the drafted registry) in a staging folder, then swap
        them in and move to `checked`. Until the swap nothing changes, so a load refused
        for space leaves the workspace exactly as it was. A failing set loads nothing
        and goes back to `new`."""
        with self.locked(workspace.id) as fresh:
            meta = fresh.meta
            if meta.state == "confirmed":
                raise WrongStateError("This workspace is already confirmed.")
            if not meta.files:
                raise WrongStateError("Upload at least one CSV file first.")
            files = fresh.read_files()
            result = check_files(files, self.limits)
            if not result.ok:
                fresh.clear_loaded()
                meta.state = "new"
                fresh.check_path.write_text(json.dumps(result.to_dict()), encoding="utf-8")
                return result
            estimate = max(LOAD_MIN_BYTES, LOAD_FACTOR * sum(len(f.data) for f in files))
            self.capacity.reserve(estimate)
            staging = fresh.dir / f"{_STAGING}{secrets.token_hex(4)}"
            try:
                staging.mkdir()
                load_tables(result.tables, staging / fresh.db_path.name)
                extra = (
                    after_load(staging / fresh.db_path.name, result.tables) if after_load else {}
                )
                for file_name, text in extra.items():
                    (staging / file_name).write_text(text, encoding="utf-8")
                built = sum(p.stat().st_size for p in staging.iterdir())
                if not self.capacity.fits(built, held=estimate):
                    raise DiskFullError(DISK_FULL)
                fresh.clear_loaded()
                for path in staging.iterdir():
                    os.replace(path, fresh.dir / path.name)
                meta.state = "checked"
                fresh.check_path.write_text(json.dumps(result.to_dict()), encoding="utf-8")
            finally:
                shutil.rmtree(staging, ignore_errors=True)
                self.capacity.release(estimate)
        return result


def _too_large(limit: int) -> str:
    size = f"{limit // MB} MB" if limit >= MB else f"{limit:,} bytes"
    return f"A file can be at most {size}. Split it into smaller files."
