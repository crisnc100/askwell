"""Starter questions for a confirmed workspace, made from its own tables and columns by
templates. No model is called. Each starter carries the intent its question means, and
it is offered only if that intent passes the validator and the SQL builder, so every
starter is a question the grammar can answer."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime

from askwell.core.intent import GroupBy, Intent, Metric, OrderBy
from askwell.core.registry import Registry
from askwell.core.sqlbuild import build
from askwell.core.validate import validate
from askwell.workspace.fields import FieldInfo

log = logging.getLogger("askwell.workspace")

MAX_STARTERS = 5
NUMBER_TYPES = frozenset({"integer", "number"})
DATE_TYPES = frozenset({"date", "datetime"})


@dataclass(frozen=True)
class Starter:
    question: str
    intent: Intent


@dataclass(frozen=True)
class _Field:
    entity: str
    name: str
    type: str
    words: str
    category: bool
    aggregatable: bool

    @property
    def ref(self) -> str:
        return f"{self.entity}.{self.name}"


def _words(text: str) -> str:
    return " ".join(text.replace("_", " ").split())


def _fields(registry: Registry, info: FieldInfo) -> dict[str, list[_Field]]:
    """Each entity's visible fields, without keys and links: an id makes a poor example."""
    keys = {(slug, key) for slug, e in registry.entities.items() for key in e.primary_key}
    for rel in registry.relationships:
        keys.add((rel.from_entity, rel.from_field))
        keys.add((rel.to_entity, rel.to_field))
    out: dict[str, list[_Field]] = {}
    for slug, entity in registry.entities.items():
        out[slug] = [
            _Field(
                entity=slug,
                name=name,
                type=fdef.type,
                words=_words(info.headers.get(f"{slug}.{name}", name)),
                # A category is a text field with few enough values to list. Its values may be
                # held back from the model; only its name goes in the question.
                category=fdef.type == "text" and f"{slug}.{name}" in info.values,
                aggregatable=fdef.aggregatable,
            )
            for name, fdef in entity.fields.items()
            if not fdef.hidden and (slug, name) not in keys
        ]
    return out


def _candidates(fields: dict[str, list[_Field]]) -> Iterator[Starter]:
    numbers = {
        e: [f for f in fs if f.type in NUMBER_TYPES and f.aggregatable] for e, fs in fields.items()
    }
    categories = [f for fs in fields.values() for f in fs if f.category]

    if categories:
        cat = categories[0]
        yield Starter(
            f"How many {_words(cat.entity)} are there by {cat.words}?",
            Intent(
                intent_type="grouped_summary",
                entity=cat.entity,
                metrics=[Metric(agg="count", alias="count")],
                group_by=[GroupBy(field=cat.ref)],
                order_by=[OrderBy(target="count", direction="desc")],
            ),
        )

    for entity, nums in numbers.items():
        dates = [f for f in fields[entity] if f.type in DATE_TYPES]
        if nums and dates:
            num, date = nums[0], dates[0]
            yield Starter(
                f"What is the total {num.words} by month of {date.words}?",
                Intent(
                    intent_type="grouped_summary",
                    entity=entity,
                    metrics=[Metric(agg="sum", field=num.ref, alias="total")],
                    group_by=[GroupBy(field=date.ref, grain="month")],
                ),
            )
            break

    # The top five reads best for a table with a name-like text column to show.
    ranked = sorted(
        (e for e, nums in numbers.items() if nums),
        key=lambda e: not any(f.type == "text" for f in fields[e]),
    )
    if ranked:
        entity = ranked[0]
        num = numbers[entity][0]
        label = next((f for f in fields[entity] if f.type == "text"), None)
        yield Starter(
            f"Which 5 {_words(entity)} have the highest {num.words}?",
            Intent(
                intent_type="row_list",
                entity=entity,
                select=[f.ref for f in (label, num) if f is not None],
                order_by=[OrderBy(target=num.ref, direction="desc")],
                limit=5,
            ),
        )

    first = categories[0].entity if categories else next(iter(fields), None)
    if first is not None:
        yield Starter(
            f"How many {_words(first)} are there?",
            Intent(intent_type="summary", entity=first, metrics=[Metric(agg="count")]),
        )

    if len(categories) > 1:
        cat = categories[1]
        yield Starter(
            f"How many {_words(cat.entity)} are there by {cat.words}?",
            Intent(
                intent_type="grouped_summary",
                entity=cat.entity,
                metrics=[Metric(agg="count", alias="count")],
                group_by=[GroupBy(field=cat.ref)],
                order_by=[OrderBy(target="count", direction="desc")],
            ),
        )

    for entity, nums in numbers.items():
        if nums:
            yield Starter(
                f"What is the average {nums[0].words} of {_words(entity)}?",
                Intent(
                    intent_type="summary",
                    entity=entity,
                    metrics=[Metric(agg="avg", field=nums[0].ref)],
                ),
            )
            break


def starters(registry: Registry, info: FieldInfo, now: datetime) -> list[Starter]:
    """Up to `MAX_STARTERS` questions about this registry's own tables and columns."""
    out: list[Starter] = []
    for candidate in _candidates(_fields(registry, info)):
        if candidate.question in {s.question for s in out}:
            continue
        result = validate(candidate.intent, registry, now=now, allow_draft=False)
        if not result.ok or result.plan is None:
            continue
        try:
            build(result.plan)
        except Exception:
            # A builder bug must not take the Ask page down; the starter is left out.
            log.exception("starter %r did not build", candidate.question)
            continue
        out.append(candidate)
        if len(out) == MAX_STARTERS:
            break
    return out
