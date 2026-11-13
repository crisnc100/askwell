from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import Engine, create_engine

from askwell.config import Settings, get_settings
from askwell.core.audit import AuditLog
from askwell.core.intent import Intent
from askwell.llm.errors import ParseError
from askwell.llm.types import ChatMessage, LLMResult, RawResponse
from askwell.pipeline.service import AskService, SchemaConfig
from tests.core.conftest import FIELDSERVICE_REGISTRY


class ScriptedGateway:
    """A test double for the model gateway: returns scripted intents in order and records
    the messages it was given. Used only where a recording cannot express the case
    (e.g. a first answer that fails validation). It is never written to the replay store."""

    mode = "replay"
    guard = None

    def __init__(self, answers: list[dict[str, Any] | str]) -> None:
        self.answers = list(answers)
        self.calls: list[list[ChatMessage]] = []

    def complete(self, *, messages: list[ChatMessage], **_: Any) -> LLMResult[Intent]:
        self.calls.append(messages)
        answer = self.answers.pop(0)
        content = answer if isinstance(answer, str) else json.dumps(answer)
        raw = RawResponse(content=content, parsed=None, usage={}, model="test/double")
        try:
            value = Intent.model_validate_json(content)
        except ValueError as exc:
            raise ParseError("not an intent", content) from exc
        return LLMResult[Intent](
            value=value, raw=raw, cost_usd=0.001, cost_source="replay", replayed=True, key="k"
        )


@pytest.fixture
def settings() -> Settings:
    return get_settings()


@pytest.fixture
def audit_engine(tmp_path: Path) -> Iterator[Engine]:
    engine = create_engine(f"sqlite:///{tmp_path / 'app.sqlite'}")
    yield engine
    engine.dispose()


@pytest.fixture
def fieldservice_config(sqlite_fieldservice: Engine) -> dict[str, SchemaConfig]:
    return {
        "fieldservice": SchemaConfig(
            id="fieldservice",
            title="Field service",
            registry_path=FIELDSERVICE_REGISTRY,
            db_url=str(sqlite_fieldservice.url),
        )
    }


def scripted_service(
    settings: Settings,
    schemas: dict[str, SchemaConfig],
    answers: list[dict[str, Any] | str],
    audit_engine: Engine,
) -> tuple[AskService, ScriptedGateway]:
    gateway = ScriptedGateway(answers)
    service = AskService(settings, schemas, gateway, AuditLog(audit_engine), model="test/double")  # type: ignore[arg-type]
    return service, gateway
