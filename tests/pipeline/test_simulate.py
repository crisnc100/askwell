"""Export/import of simulated answers. The answers written here are synthetic fixtures
for the import mechanism, in a temp directory; they never reach the committed store."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import BaseModel

from ledgerline.llm.errors import ParseError
from ledgerline.llm.gateway import Gateway
from ledgerline.llm.replay import ReplayStore
from ledgerline.llm.simulate import (
    AnswerImportError,
    PendingRequestError,
    answer_path,
    import_answers,
    pending_requests,
)
from ledgerline.llm.types import ChatMessage


class Pick(BaseModel):
    choice: str


MESSAGES = [
    ChatMessage(role="system", content="You pick."),
    ChatMessage(role="user", content="a or b?"),
]


def _gateway(mode: str, tmp_path: Path) -> Gateway:
    return Gateway(
        mode=mode,  # type: ignore[arg-type]
        store=ReplayStore(tmp_path / "store.jsonl"),
        transport=None,
        price_lookup=lambda _m: None,
        guard=None,
        max_tokens=100,
        pending_dir=tmp_path / "pending",
    )


def _complete(gw: Gateway):
    return gw.complete(
        model="target/model",
        prompt_version="p1",
        messages=MESSAGES,
        schema=Pick,
        context={"question": "a or b?"},
    )


def _answer(tmp_path: Path, key: str, **body: object) -> None:
    answer_path(tmp_path / "pending", key).write_text(json.dumps({"key": key, **body}))


def test_export_writes_the_full_request(tmp_path: Path) -> None:
    with pytest.raises(PendingRequestError) as info:
        _complete(_gateway("export", tmp_path))
    request = json.loads(info.value.path.read_text())
    assert request["key"] == info.value.key
    assert request["target_model"] == "target/model"
    assert request["prompt_version"] == "p1"
    assert request["system_prompt"] == "You pick."
    assert request["messages"] == [m.model_dump() for m in MESSAGES]
    assert request["response_schema"] == Pick.model_json_schema()
    assert request["context"] == {"question": "a or b?"}
    assert request["answer_file"] == f"{info.value.key}.answer.json"


def test_import_then_replay_carries_provenance(tmp_path: Path) -> None:
    with pytest.raises(PendingRequestError) as info:
        _complete(_gateway("export", tmp_path))
    key = info.value.key
    _answer(tmp_path, key, simulated_by="claude-test", response={"choice": "a"})
    imported = import_answers(tmp_path / "pending", ReplayStore(tmp_path / "store.jsonl"))
    assert [(i.key, i.simulated_by, i.standing_in_for) for i in imported] == [
        (key, "claude-test", "target/model")
    ]
    assert pending_requests(tmp_path / "pending") == []
    result = _complete(_gateway("replay", tmp_path))
    assert result.value == Pick(choice="a")
    assert result.provenance == {"simulated_by": "claude-test", "standing_in_for": "target/model"}
    assert result.cost_usd == 0.0
    # Export mode answers recorded keys from the store instead of exporting again.
    assert _complete(_gateway("export", tmp_path)).value == Pick(choice="a")


def test_a_text_answer_replays_as_a_parse_error(tmp_path: Path) -> None:
    with pytest.raises(PendingRequestError) as info:
        _complete(_gateway("export", tmp_path))
    _answer(tmp_path, info.value.key, simulated_by="claude-test", response_text="I think a.")
    import_answers(tmp_path / "pending", ReplayStore(tmp_path / "store.jsonl"))
    with pytest.raises(ParseError):
        _complete(_gateway("replay", tmp_path))


def test_unanswered_requests_stay_pending(tmp_path: Path) -> None:
    with pytest.raises(PendingRequestError):
        _complete(_gateway("export", tmp_path))
    assert import_answers(tmp_path / "pending", ReplayStore(tmp_path / "s.jsonl")) == []
    assert len(pending_requests(tmp_path / "pending")) == 1


@pytest.mark.parametrize(
    ("body", "message"),
    [
        ({"simulated_by": "c", "response": {}, "key": "other"}, "key"),
        ({"response": {"choice": "a"}}, "simulated_by"),
        ({"simulated_by": "c"}, "one of"),
        ({"simulated_by": "c", "response": {}, "response_text": "x"}, "one of"),
    ],
)
def test_bad_answers_are_rejected(tmp_path: Path, body: dict[str, object], message: str) -> None:
    with pytest.raises(PendingRequestError) as info:
        _complete(_gateway("export", tmp_path))
    key = info.value.key
    answer_path(tmp_path / "pending", key).write_text(json.dumps({"key": key, **body}))
    with pytest.raises(AnswerImportError, match=message):
        import_answers(tmp_path / "pending", ReplayStore(tmp_path / "s.jsonl"))


def test_export_mode_needs_a_pending_dir(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="pending"):
        Gateway(
            mode="export",
            store=ReplayStore(tmp_path / "s"),
            transport=None,
            price_lookup=lambda _m: None,
            guard=None,
            max_tokens=1,
        )
