"""The HTTP API: POST /ask, GET /schemas, GET /schemas/{id}/examples, GET /healthz, the
workspace routes under /api (ledgerline/workspace/api.py) and the Results page's report
routes (ledgerline/bench/results.py)."""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from ledgerline.bench import results
from ledgerline.config import get_settings
from ledgerline.llm.errors import ReplayMissError
from ledgerline.llm.simulate import PendingRequestError
from ledgerline.pipeline.service import AskService, UnknownSchemaError
from ledgerline.workspace import api as workspace_api
from ledgerline.workspace.api import WorkspaceApp
from ledgerline.workspace.store import WorkspaceStore


class AskRequest(BaseModel):
    schema_id: str
    question: str = Field(min_length=1, max_length=2000)


WEB_DIST = Path(__file__).resolve().parents[1] / "web" / "dist"


def create_app(
    service: AskService | None = None,
    workspaces: WorkspaceApp | None = None,
    web_dir: Path = WEB_DIST,
) -> FastAPI:
    """The API, plus the pages from `web_dir` at `/` when they have been built
    (`npm run build` in web/)."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if service is None:
            app.state.service = AskService.from_settings(get_settings())
        else:
            app.state.service = service
        yield
        app.state.service.close()

    app = FastAPI(title="Ledgerline", version="0.1.0", lifespan=lifespan)
    if workspaces is None:
        settings = get_settings()
        workspaces = WorkspaceApp(
            WorkspaceStore(Path(settings.workspace_dir)),
            trust_proxy=settings.trust_proxy,
            prompt_budget_chars=settings.prompt_budget_chars,
        )
    app.state.workspaces = workspaces

    @app.middleware("http")
    async def _headers(  # pyright: ignore[reportUnusedFunction]
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response = await call_next(request)
        # The workspace link is a secret: never send any URL of this site onward.
        response.headers["Referrer-Policy"] = "no-referrer"
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    workspace_api.install(app, workspaces)
    results.install(app)

    def svc() -> AskService:
        return app.state.service  # type: ignore[no-any-return]

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok", "mode": svc().gateway.mode}

    @app.get("/schemas")
    def schemas() -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for config in svc().schemas.values():
            out.append({"id": config.id, "title": config.title, "draft": config.allow_draft})
        return out

    @app.get("/schemas/{schema_id}/examples")
    def examples(schema_id: str) -> list[str]:
        config = svc().schemas.get(schema_id)
        if config is None:
            raise HTTPException(404, f"unknown schema {schema_id!r}")
        return config.examples

    @app.post("/ask")
    def ask(request: AskRequest, http: Request) -> dict[str, Any]:
        workspaces.check_ask_rate(http)
        try:
            return svc().ask(request.schema_id, request.question).to_dict()
        except UnknownSchemaError as exc:
            raise HTTPException(404, f"unknown schema {request.schema_id!r}") from exc
        except PendingRequestError as exc:
            raise HTTPException(409, f"exported for a simulated answer: {exc.path.name}") from exc
        except ReplayMissError as exc:
            raise HTTPException(
                409,
                "no recorded model answer for this question; replay mode answers the "
                "canned examples (GET /schemas/{id}/examples)",
            ) from exc

    if web_dir.is_dir():
        # Mounted last, so every API route above takes precedence over a file path.
        app.mount("/", StaticFiles(directory=web_dir, html=True), name="web")

    return app
