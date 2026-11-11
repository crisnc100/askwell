"""A stand-in for the live model in workspace tests: it answers each question with an
intent chosen by the test and keeps every request it was sent. It reports `live` mode,
because a workspace answers only with a live model."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from typing import Any

from ledgerline.config import Settings
from ledgerline.core.intent import Intent
from ledgerline.llm.errors import ParseError
from ledgerline.llm.types import ChatMessage, LLMResult, RawResponse
from ledgerline.pipeline.service import AskService

UNANSWERABLE = {"intent_type": "unanswerable", "unanswerable_reason": "not in the data"}

Answer = dict[str, Any] | str


class FakeModel:
    mode = "live"
    guard = None

    def __init__(
        self, answers: Mapping[str, Answer] | Callable[[str], Answer] | None = None
    ) -> None:
        self.answers: Mapping[str, Answer] | Callable[[str], Answer] = answers or {}
        self.calls: list[list[ChatMessage]] = []

    def complete(self, *, messages: list[ChatMessage], **_: Any) -> LLMResult[Intent]:
        self.calls.append(messages)
        question = next(m.content for m in messages if m.role == "user")
        if callable(self.answers):
            answer = self.answers(question)
        else:
            answer = self.answers.get(question, UNANSWERABLE)
        content = answer if isinstance(answer, str) else json.dumps(answer)
        raw = RawResponse(content=content, parsed=None, usage={}, model="test/fake")
        try:
            value = Intent.model_validate_json(content)
        except ValueError as exc:
            raise ParseError("not an intent", content) from exc
        return LLMResult[Intent](
            value=value, raw=raw, cost_usd=0.0, cost_source="replay", replayed=False, key="fake"
        )

    @property
    def system_prompts(self) -> list[str]:
        return [call[0].content for call in self.calls]


def fake_service(settings: Settings, model: FakeModel) -> AskService:
    return AskService(settings, {}, model, None, model="test/fake")  # type: ignore[arg-type]
