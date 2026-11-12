"""Recorded model responses, so tests, CI and demos run with no API key.

Two stores share one JSONL format (one `{"key", "record"}` object per line, last
write wins):

- `ReplayStore` for structured calls, keyed by hash(model, prompt_version,
  messages, schema).
- `TrajectoryStore` for agent baselines, keyed by (system, question_id, model,
  prompt_version). An agent's messages contain DB rows whose order can vary, so
  hashing messages would miss on every re-run; the question identity is stable.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from askwell.llm.errors import ReplayMissError
from askwell.llm.types import ChatMessage


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def replay_key(
    model: str, prompt_version: str, messages: list[ChatMessage], schema: dict[str, Any]
) -> str:
    payload = {
        "model": model,
        "prompt_version": prompt_version,
        "messages": [m.model_dump() for m in messages],
        "schema": schema,
    }
    return hashlib.sha256(canonical_json(payload).encode()).hexdigest()


def trajectory_key(system: str, question_id: str, model: str, prompt_version: str) -> str:
    for part in (system, question_id, model, prompt_version):
        if not part or "|" in part:
            raise ValueError(f"trajectory key part must be non-empty without '|': {part!r}")
    return "|".join((system, question_id, model, prompt_version))


class JsonlStore:
    def __init__(self, path: Path | str, what: str) -> None:
        self.path = Path(path)
        self._what = what
        self._records: dict[str, dict[str, Any]] = {}
        if self.path.exists():
            with self.path.open(encoding="utf-8") as fh:
                for line in fh:
                    if line.strip():
                        entry = json.loads(line)
                        self._records[entry["key"]] = entry["record"]

    def __contains__(self, key: str) -> bool:
        return key in self._records

    def __len__(self) -> int:
        return len(self._records)

    def get(self, key: str) -> dict[str, Any]:
        try:
            return self._records[key]
        except KeyError:
            raise ReplayMissError(key, self._what) from None

    def put(self, key: str, record: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(canonical_json({"key": key, "record": record}) + "\n")
        self._records[key] = record


class ReplayStore(JsonlStore):
    def __init__(self, path: Path | str) -> None:
        super().__init__(path, "call")


class TrajectoryStore(JsonlStore):
    def __init__(self, path: Path | str) -> None:
        super().__init__(path, "agent trajectory")

    def get_trajectory(
        self, system: str, question_id: str, model: str, prompt_version: str
    ) -> dict[str, Any]:
        return self.get(trajectory_key(system, question_id, model, prompt_version))

    def put_trajectory(
        self,
        system: str,
        question_id: str,
        model: str,
        prompt_version: str,
        trajectory: dict[str, Any],
    ) -> None:
        self.put(trajectory_key(system, question_id, model, prompt_version), trajectory)
