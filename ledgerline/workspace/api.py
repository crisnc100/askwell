"""The workspace HTTP routes, under `/api`.

The workspace id travels only in the `X-Workspace-Id` header, and a file name only in
`X-File-Name` (percent-encoded UTF-8), never in a request URL, so they stay out of access
logs and Referer headers. The page keeps it after the link's `#`,
which browsers never send. Every refusal comes back as `{"detail": <a plain sentence>}`
with a status the page can show as is.
"""

from __future__ import annotations

import asyncio
import json
import threading
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import unquote

from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, ValidationError

from ledgerline.workspace import fields
from ledgerline.workspace.ask import ask_workspace, prompt_preview
from ledgerline.workspace.fields import Edits
from ledgerline.workspace.limits import Limits, RateLimiter
from ledgerline.workspace.store import (
    DEFAULT_TIME_ZONE,
    Workspace,
    WorkspaceError,
    WorkspaceStore,
    time_zones,
)

HEADER = "X-Workspace-Id"
FILE_HEADER = "X-File-Name"
HOUR_S = 3600.0


class TooManyRequestsError(WorkspaceError):
    status = 429


class NotJsonError(WorkspaceError):
    status = 415


@dataclass
class WorkspaceApp:
    """What the workspace routes need: the store and the per-IP rate limiters."""

    store: WorkspaceStore
    # Trust X-Forwarded-For (set LEDGERLINE_TRUST_PROXY=1 only behind a proxy that sets it).
    trust_proxy: bool = False
    # The interpret prompt's size budget (Settings.prompt_budget_chars); the Confirm
    # preview truncates exactly as the prompt does.
    prompt_budget_chars: int = 16000
    uploads: RateLimiter = field(init=False)
    asks: RateLimiter = field(init=False)
    checks: RateLimiter = field(init=False)
    _in_flight: dict[str, int] = field(init=False, default_factory=dict[str, int])
    _in_flight_lock: threading.Lock = field(init=False, default_factory=threading.Lock)

    def __post_init__(self) -> None:
        limits = self.limits
        self.uploads = RateLimiter(limits.uploads_per_hour, HOUR_S)
        self.asks = RateLimiter(limits.asks_per_hour, HOUR_S)
        self.checks = RateLimiter(limits.checks_per_hour, HOUR_S)

    @contextmanager
    def upload_slot(self, ip: str) -> Generator[None]:
        """Hold one of the address's concurrent upload slots for the upload's length."""
        with self._in_flight_lock:
            if self._in_flight.get(ip, 0) >= self.limits.uploads_in_flight_per_ip:
                raise TooManyRequestsError(
                    "Your address already has uploads running. Wait for them to finish."
                )
            self._in_flight[ip] = self._in_flight.get(ip, 0) + 1
        try:
            yield
        finally:
            with self._in_flight_lock:
                self._in_flight[ip] -= 1
                if not self._in_flight[ip]:
                    del self._in_flight[ip]

    @property
    def limits(self) -> Limits:
        return self.store.limits

    def check_ask_rate(self, request: Request) -> None:
        if not self.asks.allow(self.client_ip(request)):
            raise TooManyRequestsError(
                f"Too many questions from your address (the limit is "
                f"{self.limits.asks_per_hour} an hour). Try again later."
            )

    def client_ip(self, request: Request) -> str:
        """The caller's address. Behind a trusted proxy it is the last X-Forwarded-For
        entry, the one the proxy itself appended; earlier entries are whatever the
        client sent."""
        if self.trust_proxy:
            # Every header line counts: a client can add its own line, but the proxy's
            # value is always last.
            forwarded = ",".join(request.headers.getlist("x-forwarded-for"))
            last = forwarded.split(",")[-1].strip()
            if last:
                return last
        return request.client.host if request.client else "unknown"


class CreateRequest(BaseModel):
    time_zone: str = DEFAULT_TIME_ZONE


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)


def status(app: WorkspaceApp, workspace: Workspace) -> dict[str, Any]:
    meta = workspace.meta
    check = None
    if workspace.check_path.exists():
        check = json.loads(workspace.check_path.read_text(encoding="utf-8"))
    return {
        "id": meta.id,
        "state": meta.state,
        "time_zone": meta.time_zone,
        "created_at": meta.created_at,
        "expires_at": app.store.expires_at(meta).isoformat(),
        "files": [{"name": f.name, "bytes": f.bytes} for f in meta.files],
        "check": check,
    }


def install(fastapi_app: FastAPI, app: WorkspaceApp) -> APIRouter:
    """Add the workspace routes and their error handler to `fastapi_app`."""
    router = APIRouter(prefix="/api")

    @fastapi_app.exception_handler(WorkspaceError)
    async def _refused(_request: Request, exc: WorkspaceError) -> JSONResponse:  # pyright: ignore[reportUnusedFunction]
        return JSONResponse({"detail": exc.message}, status_code=exc.status)

    def opened(request: Request) -> Workspace:
        return app.store.open(request.headers.get(HEADER))

    def file_name(request: Request) -> str:
        raw = request.headers.get(FILE_HEADER)
        if raw is None:
            raise WorkspaceError(f"Send the file name in the {FILE_HEADER} header.")
        try:
            return unquote(raw, errors="strict")
        except UnicodeDecodeError as exc:
            raise WorkspaceError("Send the file name percent-encoded as UTF-8.") from exc

    @router.get("/time-zones")
    def list_time_zones() -> list[str]:
        return sorted(time_zones())

    @router.get("/limits")
    def limits() -> dict[str, int]:
        lim = app.limits
        return {
            "max_file_bytes": lim.max_file_bytes,
            "max_files": lim.max_files,
            "max_columns": lim.max_columns,
            "max_rows": lim.max_rows,
            "max_cell_chars": lim.max_cell_chars,
            "idle_days": lim.idle_days,
        }

    @router.post("/workspaces", status_code=201)
    async def create(request: Request) -> dict[str, Any]:
        # A cross-site page can send a form or an empty POST without the browser asking
        # first, but not JSON, so requiring JSON keeps other sites from creating
        # workspaces on a visitor's behalf. The type is checked before the body is read.
        content_type = request.headers.get("content-type", "").split(";")[0].strip().lower()
        if content_type != "application/json":
            raise NotJsonError("Send the request as JSON.")
        try:
            body = CreateRequest.model_validate_json(await request.body() or b"{}")
        except ValidationError as exc:
            raise WorkspaceError("Send a JSON object, optionally with a time_zone.") from exc
        workspace = await asyncio.to_thread(
            app.store.create, app.client_ip(request), body.time_zone
        )
        return status(app, workspace)

    @router.get("/workspace")
    def show(request: Request) -> dict[str, Any]:
        return status(app, opened(request))

    @router.put("/workspace/files")
    async def upload(request: Request) -> dict[str, Any]:
        # Opening takes the workspace lock, so it runs off the event loop.
        workspace = await asyncio.to_thread(opened, request)
        ip = app.client_ip(request)
        if not app.uploads.allow(ip):
            raise TooManyRequestsError(
                f"Too many uploads from your address (the limit is "
                f"{app.limits.uploads_per_hour} an hour). Try again later."
            )
        length = request.headers.get("content-length")
        with app.upload_slot(ip):
            await app.store.upload(
                workspace,
                file_name(request),
                request.stream(),
                int(length) if length and length.isdigit() else None,
            )
        fresh = await asyncio.to_thread(app.store.open, workspace.id, touch=False)
        return status(app, fresh)

    @router.delete("/workspace/files")
    def remove_file(request: Request) -> dict[str, Any]:
        workspace = opened(request)
        app.store.remove_file(workspace, file_name(request))
        return status(app, app.store.open(workspace.id, touch=False))

    @router.post("/workspace/check")
    def check(request: Request) -> dict[str, Any]:
        workspace = opened(request)
        if not app.checks.allow(app.client_ip(request)):
            raise TooManyRequestsError(
                f"Too many checks from your address (the limit is "
                f"{app.limits.checks_per_hour} an hour). Try again later."
            )
        app.store.check(workspace, after_load=fields.draft)
        return status(app, app.store.open(workspace.id, touch=False))

    @router.get("/workspace/fields")
    def list_fields(request: Request) -> dict[str, Any]:
        workspace = opened(request)
        registry, info = fields.load_draft(workspace)
        edits = fields.saved_edits(workspace)
        return {"tables": fields.field_rows(registry, info, edits), "edits": edits.model_dump()}

    @router.post("/workspace/preview")
    def preview(request: Request, edits: Edits) -> dict[str, Any]:
        workspace = opened(request)
        registry, info = fields.load_draft(workspace)
        applied = fields.apply(registry, info, edits)
        return prompt_preview(
            applied, workspace.meta.time_zone, app.store.clock, app.prompt_budget_chars
        )

    @router.post("/workspace/confirm")
    def confirm(request: Request, edits: Edits) -> dict[str, Any]:
        workspace = opened(request)
        fields.confirm(app.store, workspace, edits)
        return status(app, app.store.open(workspace.id, touch=False))

    @router.post("/workspace/ask")
    def ask(request: Request, body: AskRequest) -> dict[str, Any]:
        workspace = opened(request)
        app.check_ask_rate(request)
        return ask_workspace(request.app.state.service, workspace, body.question, app.store.clock)

    @router.delete("/workspace")
    def delete(request: Request) -> dict[str, bool]:
        workspace = app.store.open(request.headers.get(HEADER), touch=False)
        return {"deleted": app.store.delete(workspace.id)}

    fastapi_app.include_router(router)
    return router
