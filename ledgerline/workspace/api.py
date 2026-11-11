"""The workspace HTTP routes, under `/api`.

The workspace id travels only in the `X-Workspace-Id` header, never in a URL, so it
stays out of access logs, browser history and Referer headers. Every refusal comes back
as `{"detail": <a plain sentence>}` with a status the page can show as is.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

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
HOUR_S = 3600.0


class TooManyRequestsError(WorkspaceError):
    status = 429


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

    def __post_init__(self) -> None:
        limits = self.limits
        self.uploads = RateLimiter(limits.uploads_per_hour, HOUR_S)
        self.asks = RateLimiter(limits.asks_per_hour, HOUR_S)

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
            forwarded = request.headers.get("x-forwarded-for", "")
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
    def create(request: Request, body: CreateRequest | None = None) -> dict[str, Any]:
        chosen = body.time_zone if body is not None else DEFAULT_TIME_ZONE
        workspace = app.store.create(app.client_ip(request), chosen)
        return status(app, workspace)

    @router.get("/workspace")
    def show(request: Request) -> dict[str, Any]:
        return status(app, opened(request))

    @router.put("/workspace/files")
    async def upload(request: Request, name: str) -> dict[str, Any]:
        workspace = opened(request)
        if not app.uploads.allow(app.client_ip(request)):
            raise TooManyRequestsError(
                f"Too many uploads from your address (the limit is "
                f"{app.limits.uploads_per_hour} an hour). Try again later."
            )
        length = request.headers.get("content-length")
        await app.store.upload(
            workspace,
            name,
            request.stream(),
            int(length) if length and length.isdigit() else None,
        )
        return status(app, workspace)

    @router.delete("/workspace/files")
    def remove_file(request: Request, name: str) -> dict[str, Any]:
        workspace = opened(request)
        app.store.remove_file(workspace, name)
        return status(app, workspace)

    @router.post("/workspace/check")
    def check(request: Request) -> dict[str, Any]:
        workspace = opened(request)
        app.store.check(workspace, after_load=fields.draft)
        return status(app, workspace)

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
        return status(app, workspace)

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
