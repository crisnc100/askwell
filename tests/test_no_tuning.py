"""G7, no tuning to the gold: no run of 6 words from any gold question (seen or held
out) appears in the interpret prompt, a registry description or an alias. Words are
compared lowercased, with punctuation dropped."""

from __future__ import annotations

import json
import re
from pathlib import Path

from askwell.core.registry import Registry, load_registry

ROOT = Path(__file__).resolve().parent.parent
GOLD = ROOT / "evals" / "gold"
RUN = 6


def _words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def _runs(text: str) -> set[str]:
    words = _words(text)
    return {" ".join(words[i : i + RUN]) for i in range(len(words) - RUN + 1)}


def _questions() -> list[str]:
    out: list[str] = []
    for path in sorted(GOLD.glob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                out.append(json.loads(line)["question"])
    return out


def _registry_text(registry: Registry) -> list[str]:
    out: list[str] = []
    for entity in registry.entities.values():
        out += [entity.description, *entity.aliases]
        for field in entity.fields.values():
            out += [field.description, *field.aliases, *field.value_aliases]
    return out


def _leaks(targets: list[str], questions: list[str]) -> list[str]:
    joined = " " + " | ".join(" ".join(_words(t)) for t in targets) + " "
    found: set[str] = set()
    for question in questions:
        found |= {run for run in _runs(question) if f" {run} " in joined}
    return sorted(found)


def test_the_checker_finds_a_planted_run() -> None:
    question = "How many widgets shipped to the north depot last spring?"
    assert _leaks(["Example: many widgets shipped to the north depot."], [question]) == [
        "many widgets shipped to the north",
        "widgets shipped to the north depot",
    ]
    assert _leaks(["widgets shipped to the north"], [question]) == []


def test_no_gold_question_run_is_in_the_prompt_or_registries() -> None:
    questions = _questions()
    assert len(questions) >= 67  # the seen set; the held-out set joins it in Phase 4
    targets = [(ROOT / "askwell" / "pipeline" / "prompt.py").read_text(encoding="utf-8")]
    for path in sorted((ROOT / "registries").glob("*.yaml")):
        targets += _registry_text(load_registry(path))
    assert _leaks(targets, questions) == []
