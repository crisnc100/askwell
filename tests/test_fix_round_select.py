"""PR5 review fixes: model selection when every candidate fails a gate, vendors across
providers, the replay command ADR-004 documents, and pinned Docker base images."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from scripts.select_model import Candidate, choose

ROOT = Path(__file__).resolve().parent.parent


def _cand(model: str, cost: float, correct: int, **kw: Any) -> Candidate:
    base: dict[str, Any] = {
        "questions": 67,
        "answerable": 43,
        "wrong": 2,
        "refusals_caught": 24,
        "refusal_items": 24,
        "calls": 100,
        "unreadable": 0,
        "p50_ms": 1000.0,
    }
    base.update(kw)
    return Candidate(model=model, cost_per_question=cost, correct=correct, **base)


def test_when_every_candidate_fails_a_gate_the_best_one_ships() -> None:
    choice = choose(
        [_cand("a/cheap", 0.001, 32, p50_ms=5000.0), _cand("c/best", 0.01, 35, p50_ms=5000.0)]
    )
    assert choice.eligible == []
    assert choice.default.model == "c/best"


def test_direct_and_routed_anthropic_models_are_the_same_vendor() -> None:
    choice = choose(
        [
            _cand("anthropic:claude-x", 0.001, 35),
            _cand("anthropic/claude-x", 0.002, 34),
            _cand("google/gemma", 0.003, 30),
        ]
    )
    assert choice.default.model == "anthropic:claude-x"
    assert choice.second is not None
    assert choice.second.model == "google/gemma"


def test_the_adr_replay_commands_name_the_schema_and_every_model() -> None:
    text = (ROOT / "docs" / "adr" / "ADR-004-model-choice.md").read_text()
    four = (
        "mistralai/mistral-small-24b-instruct-2501,google/gemma-4-26b-a4b-it,"
        "openai/gpt-oss-120b,openai/gpt-4o-mini"
    )
    assert (
        "askwell eval --schema fieldservice --systems ledgerline,oneshot --mode replay "
        f"--models {four} --trials 1 --run-id select-2026-11-11"
    ) in text
    assert (
        "askwell eval --schema fieldservice --systems ledgerline,oneshot --mode replay "
        "--models anthropic:claude-haiku-5-5 --trials 1 --run-id select-haiku-2026-11-11"
    ) in text


def test_docker_base_images_are_pinned_by_digest() -> None:
    froms = re.findall(r"^FROM (\S+)", (ROOT / "Dockerfile").read_text(), re.MULTILINE)
    assert len(froms) == 2
    for image in froms:
        assert re.search(r"@sha256:[0-9a-f]{64}$", image), image
