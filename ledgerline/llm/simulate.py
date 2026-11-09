"""Simulated model answers (plan.md, Decision 2026-11-09: no OpenRouter key yet).

`export` writes each unrecorded request to `<pending>/<key>.json`. Someone outside this
codebase (the orchestrator's Claude subagent) answers each one as the target model
would and writes `<pending>/<key>.answer.json`:

    {"key": "<key>", "simulated_by": "<claude model id>",
     "response": {...}}            # the JSON object the model returned, or
     "response_text": "..."        # raw text, when the answer is not a JSON object

`import_answers` loads the answers into the replay store with provenance
`{"simulated_by", "standing_in_for"}`. A "response" must validate against the request's
response schema; one that does not is rejected, left on disk and reported. A
"response_text" answer claims no schema and replays as a parse error. This module never
invents an answer.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError

from ledgerline.llm.errors import LLMError
from ledgerline.llm.replay import ReplayStore
from ledgerline.llm.types import ChatMessage, RawResponse

ANSWER_INSTRUCTIONS = (
    "Answer as the target model would, given exactly these messages. Return one JSON "
    "object that matches response_schema. Write it to answer_file as "
    '{"key": <key>, "simulated_by": <your model id>, "response": <the object>}; '
    'if the honest answer is not a JSON object, use "response_text" instead.'
)


class PendingRequestError(LLMError):
    """Export mode: the request had no recording, so it was written out for an answer."""

    def __init__(self, key: str, path: Path) -> None:
        super().__init__(f"no recording for {key}; request exported to {path}")
        self.key = key
        self.path = path


class AnswerImportError(LLMError):
    """An answer file is malformed or does not match its request."""


def request_path(pending_dir: Path, key: str) -> Path:
    return pending_dir / f"{key}.json"


def answer_path(pending_dir: Path, key: str) -> Path:
    return pending_dir / f"{key}.answer.json"


def export_request(
    pending_dir: Path,
    *,
    key: str,
    model: str,
    prompt_version: str,
    messages: list[ChatMessage],
    schema_name: str,
    response_schema: dict[str, Any],
    context: dict[str, Any] | None = None,
) -> Path:
    pending_dir.mkdir(parents=True, exist_ok=True)
    path = request_path(pending_dir, key)
    system = [m.content for m in messages if m.role == "system"]
    body = {
        "key": key,
        "target_model": model,
        "prompt_version": prompt_version,
        "system_prompt": system[0] if system else "",
        "messages": [m.model_dump() for m in messages],
        "response_schema_name": schema_name,
        "response_schema": response_schema,
        "context": context or {},
        "instructions": ANSWER_INSTRUCTIONS,
        "answer_file": answer_path(pending_dir, key).name,
    }
    path.write_text(json.dumps(body, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def pending_requests(pending_dir: Path) -> list[Path]:
    return sorted(p for p in pending_dir.glob("*.json") if not p.name.endswith(".answer.json"))


_RESPONSE_MODELS: dict[str, type[BaseModel]] = {}


def register_response_model(model: type[BaseModel]) -> None:
    """Make `model` available to validate imported answers whose request named it."""
    _RESPONSE_MODELS[model.__name__] = model


def _schema_problem(request: dict[str, Any], response: Any) -> str | None:
    name = str(request.get("response_schema_name", ""))
    model = _RESPONSE_MODELS.get(name)
    if model is None:
        return f"no response model named {name!r} is registered"
    if model.model_json_schema() != request.get("response_schema"):
        return f"the request's {name} schema differs from the current one; re-export it"
    try:
        model.model_validate(response)
    except ValidationError as exc:
        first = exc.errors()[0]
        where = ".".join(str(part) for part in first["loc"]) or "(root)"
        return f"does not match {name}: {where}: {first['msg']}"
    return None


@dataclass(frozen=True)
class Rejected:
    key: str
    reason: str


@dataclass
class ImportReport:
    imported: list[Imported] = field(default_factory=list["Imported"])
    rejected: list[Rejected] = field(default_factory=list[Rejected])


@dataclass(frozen=True)
class Imported:
    key: str
    simulated_by: str
    standing_in_for: str


def import_answers(pending_dir: Path, store: ReplayStore, *, remove: bool = True) -> list[Imported]:
    """Load every valid answer into `store` and return what was imported."""
    return import_answers_report(pending_dir, store, remove=remove).imported


def import_answers_report(
    pending_dir: Path, store: ReplayStore, *, remove: bool = True
) -> ImportReport:
    """Load every answered pending request into `store`. Unanswered requests stay put;
    answers that break their response schema are rejected and stay put too."""
    report = ImportReport()
    imported = report.imported
    for request_file in pending_requests(pending_dir):
        request = json.loads(request_file.read_text(encoding="utf-8"))
        key = str(request["key"])
        answer_file = answer_path(pending_dir, key)
        if not answer_file.exists():
            continue
        answer = json.loads(answer_file.read_text(encoding="utf-8"))
        if answer.get("key") != key:
            raise AnswerImportError(f"{answer_file.name}: key {answer.get('key')!r} != {key!r}")
        simulated_by = answer.get("simulated_by")
        if not isinstance(simulated_by, str) or not simulated_by:
            raise AnswerImportError(f"{answer_file.name}: simulated_by is required")
        has_object = "response" in answer
        has_text = "response_text" in answer
        if has_object == has_text:
            raise AnswerImportError(
                f"{answer_file.name}: give exactly one of response/response_text"
            )
        if has_object:
            response = answer["response"]
            problem = _schema_problem(request, response)
            if problem is not None:
                report.rejected.append(Rejected(key, problem))
                continue
            content = json.dumps(response, ensure_ascii=False)
            parsed = response if isinstance(response, dict) else None
        else:
            content = str(answer["response_text"])
            parsed = None
        target = str(request["target_model"])
        raw = RawResponse(content=content, parsed=parsed, usage={}, model=target)
        provenance = {"simulated_by": simulated_by, "standing_in_for": target}
        store.put(
            key,
            {
                "raw": raw.model_dump(),
                "cost_usd": 0.0,
                "model": target,
                "prompt_version": request["prompt_version"],
                "provenance": provenance,
            },
        )
        imported.append(Imported(key, simulated_by, target))
        if remove:
            request_file.unlink()
            answer_file.unlink()
    return report
