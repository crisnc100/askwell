"""The HTTP API: POST /ask, GET /schemas, GET /schemas/{id}/examples, GET /healthz."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from ledgerline.config import get_settings
from ledgerline.llm.errors import ReplayMissError
from ledgerline.llm.simulate import PendingRequestError
from ledgerline.pipeline.service import AskService, UnknownSchemaError


class AskRequest(BaseModel):
    schema_id: str
    question: str = Field(min_length=1, max_length=2000)


def create_app(service: AskService | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if service is None:
            app.state.service = AskService.from_settings(get_settings())
        else:
            app.state.service = service
        yield
        app.state.service.close()

    app = FastAPI(title="Ledgerline", version="0.1.0", lifespan=lifespan)

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
    def ask(request: AskRequest) -> dict[str, Any]:
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

    return app
