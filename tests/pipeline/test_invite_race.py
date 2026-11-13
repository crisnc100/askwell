"""POST /invite takes its try before reading the body, in one step, so requests held
open cannot all start before the address is locked and finish their guesses after it.
Also: a code outside ASCII works in the X-Invite-Code header, which arrives as raw
bytes."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path
from typing import cast

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from askwell import invite
from askwell.api import create_app
from askwell.config import Settings
from askwell.core.audit import AuditLog
from askwell.llm.gateway import Gateway
from askwell.pipeline.service import AskService, SchemaConfig
from tests.pipeline.conftest import ScriptedGateway

CODES = ["alpha-123", "招待コード-7"]


@pytest.fixture
def app(
    settings: Settings,
    fieldservice_config: dict[str, SchemaConfig],
    tmp_path: Path,
    audit_engine: Engine,
) -> object:
    gateway = cast(Gateway, ScriptedGateway([]))
    service = AskService(settings, fieldservice_config, gateway, AuditLog(audit_engine), "m")
    return create_app(service, web_dir=tmp_path / "none", invite_codes=[c.encode() for c in CODES])


async def test_held_open_logins_get_at_most_the_limit_of_guesses(app: object) -> None:
    release = asyncio.Event()

    async def held_body() -> AsyncIterator[bytes]:
        yield b"code=gue"
        await release.wait()
        yield b"ss"

    transport = httpx.ASGITransport(app=app)  # type: ignore[arg-type]
    async with httpx.AsyncClient(transport=transport, base_url="https://testserver") as client:
        tasks = [
            asyncio.create_task(
                client.post(
                    "/invite",
                    content=held_body(),
                    headers={"content-type": "application/x-www-form-urlencoded"},
                )
            )
            for _ in range(30)
        ]
        await asyncio.sleep(0.2)  # every request is now waiting on its last chunk
        release.set()
        responses = await asyncio.gather(*tasks)
    codes = [r.status_code for r in responses]
    assert codes.count(401) <= invite.ATTEMPTS_PER_HOUR
    assert codes.count(429) == len(codes) - codes.count(401)


def test_a_non_ascii_code_works_in_the_header(app: object) -> None:
    with TestClient(app, base_url="https://testserver") as client:  # type: ignore[arg-type]
        raw = [(invite.HEADER.encode(), "招待コード-7".encode())]  # UTF-8 bytes on the wire
        ok = client.get("/schemas", headers=raw)
    assert ok.status_code == 200
