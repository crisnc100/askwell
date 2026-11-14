"""The HTTP API: POST /ask, GET /schemas, GET /schemas/{id}/examples, GET /healthz, the
workspace routes under /api (askwell/workspace/api.py) and the Results page's report
routes (askwell/bench/results.py). Every page and route is open to anyone; the daily
spend cap, the kill switch and the per-address limits protect spend and abuse."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import text

from askwell.bench import results
from askwell.config import get_settings
from askwell.llm.daily import DailyCapReachedError
from askwell.llm.errors import LiveAnswersOffError, ReplayMissError
from askwell.llm.simulate import PendingRequestError
from askwell.pipeline.service import AskService, UnknownSchemaError
from askwell.workspace import api as workspace_api
from askwell.workspace.api import WorkspaceApp
from askwell.workspace.store import WorkspaceStore


class AskRequest(BaseModel):
    schema_id: str
    question: str = Field(min_length=1, max_length=2000)


WEB_DIST = Path(__file__).resolve().parents[1] / "web" / "dist"

log = logging.getLogger(__name__)


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

    current = get_settings()
    if current.llm_mode == "live" and current.daily_spend_cap_usd is None:
        # Fail closed: a site anyone can reach must never answer live without a cap.
        raise RuntimeError(
            "ASKWELL_LLM_MODE is live but ASKWELL_DAILY_SPEND_CAP_USD is unset: refusing "
            "to start without a daily spending cap. Set it, for example to 1.00."
        )
    if current.invite_codes is not None:
        log.warning(
            "ASKWELL_INVITE_CODES is set but ignored: Askwell is open to everyone. "
            "Remove it from the deployment's settings."
        )
    app = FastAPI(title="Askwell", version="0.2.0", lifespan=lifespan)
    if workspaces is None:
        settings = get_settings()
        workspaces = WorkspaceApp(
            WorkspaceStore(Path(settings.workspace_dir)),
            trust_proxy=settings.trust_proxy,
            prompt_budget_chars=settings.prompt_budget_chars,
            features=settings.features,
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
    def healthz() -> JSONResponse:
        """Up, and every demo database answers. Anyone can call it, so it says nothing
        about settings, spend or data."""
        service = svc()
        broken: list[str] = []
        for schema_id in service.schemas:
            try:
                with service.engine(schema_id).connect() as conn:
                    conn.execute(text("SELECT 1"))
            except Exception:
                broken.append(schema_id)
        body: dict[str, Any] = {"status": "error" if broken else "ok", "mode": service.gateway.mode}
        if broken:
            body["unavailable"] = broken
        return JSONResponse(body, status_code=503 if broken else 200)

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
        except (LiveAnswersOffError, DailyCapReachedError) as exc:
            raise HTTPException(503, str(exc)) from exc
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
