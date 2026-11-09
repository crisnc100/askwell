"""The interpret prompt: instructions plus a compact registry view.

The view lists entities, fields and relationships in registry order. Hidden fields are
never in it. When it is over budget, truncation is deterministic: allowed values past 20
per field go first, then descriptions shorten (60 characters, then none). Every step
taken is returned so the caller can log it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from ledgerline.core.registry import FieldDef, Registry
from ledgerline.core.validate import Issue
from ledgerline.llm.types import ChatMessage

PROMPT_VERSION = "interpret-v1"
MAX_VALUES = 20
SHORT_DESCRIPTION = 60

SYSTEM_PROMPT = """\
You turn a business question about one database into a structured intent (JSON). You \
never write SQL. Code validates your intent against the registry below and writes the \
query, so use only the entities and fields listed, by their exact names.

How to fill the intent:
- intent_type: "summary" (one row of metrics), "grouped_summary" (metrics per group_by), \
"row_list" (rows of `select` fields), or "unanswerable".
- entity: the base table. Fields on other entities are written "entity.field" and are \
joined for you along the relationships listed; a bare "field" means the base entity.
- metrics: {"agg": count|count_distinct|sum|avg|min|max, "field": ..., "alias": ...}. \
count without a field counts rows. Aliases are lowercase slugs, distinct from group \
labels.
- filters: a list combined with AND. Each item is a condition {"field", "op", ...} or one \
group {"any_of": [conditions]} / {"all_of": [conditions]} (groups do not nest). \
Operators: eq, neq, gt, gte, lt, lte take "value" (or "other_field" to compare two \
fields); between takes "values": [low, high]; in takes "values": [...]; is_null takes \
"value": true (IS NULL) or false (IS NOT NULL); ilike_contains takes a text "value". \
Categorical fields list their allowed values: use one of them.
- date_range: {"field": <a date field>, "relative": <token>} with tokens today, \
yesterday, last_n_days, last_n_weeks, last_n_months (these three need "n"), this_week, \
last_week, this_month, last_month, this_quarter, last_quarter, this_year, ytd, \
last_year; or {"field", "start", "end"} as ISO dates, end exclusive. Do not compute \
dates yourself and do not also filter that field.
- group_by: [{"field", "grain"}]; grain (day, iso_week, month, quarter, year) only on \
date fields. A grouped label is the field name (or "entity__field" for joined fields), \
plus "_<grain>" when a grain is set.
- having: [{"metric": <metric alias>, "op", "value" or "values"}], only with group_by.
- order_by: [{"target": <metric alias, group label or field>, "direction": asc|desc}]; \
limit: a positive integer.
- unanswerable_reason: required, and only, for "unanswerable".

Answer "unanswerable" (with a short reason) when the data is not in the registry, when \
the question needs a field that is not listed (some fields are deliberately hidden), or \
when it asks to change data (insert, update, delete, drop). Never guess a field or a \
value that is not listed.
"""


@dataclass
class PromptView:
    text: str
    truncation: list[str] = field(default_factory=list[str])


def _field_line(name: str, fdef: FieldDef, max_values: int | None, desc_len: int | None) -> str:
    parts = [f"- {name}: {fdef.type}"]
    if fdef.aggregatable:
        parts.append(" (measure)")
    if not fdef.filterable:
        parts.append(" (not filterable)")
    if fdef.categorical and fdef.allowed_values:
        values = fdef.allowed_values
        shown = values if max_values is None else values[:max_values]
        more = f", … +{len(values) - len(shown)} more" if len(shown) < len(values) else ""
        parts.append(f", one of [{', '.join(shown)}{more}]")
    if fdef.aliases:
        parts.append(f"; aliases: {', '.join(fdef.aliases)}")
    description = fdef.description
    if desc_len is not None:
        description = description[:desc_len].rstrip() + ("…" if len(description) > desc_len else "")
    if description:
        parts.append(f" — {description}")
    return "".join(parts)


def _render(registry: Registry, now: datetime, max_values: int | None, desc_len: int | None) -> str:
    lines = [f"Reference date: {now.date().isoformat()} (UTC).", "", "Entities:"]
    for slug, entity in registry.entities.items():
        header = f"## {slug}"
        if entity.aliases:
            header += f" (aliases: {', '.join(entity.aliases)})"
        description = entity.description
        if desc_len is not None:
            description = description[:desc_len]
        if description:
            header += f" — {description}"
        lines.append(header)
        for name, fdef in entity.fields.items():
            if fdef.hidden:
                continue
            lines.append(_field_line(name, fdef, max_values, desc_len))
    if registry.relationships:
        lines += ["", "Relationships (many-to-one; joins follow them):"]
        for rel in registry.relationships:
            lines.append(f"- {rel.from_entity}.{rel.from_field} -> {rel.to_entity}.{rel.to_field}")
    return "\n".join(lines) + "\n"


def registry_view(registry: Registry, now: datetime, budget_chars: int) -> PromptView:
    steps: list[tuple[str, int | None, int | None]] = [
        ("full", None, None),
        (f"allowed values cut to {MAX_VALUES} per field", MAX_VALUES, None),
        (f"descriptions cut to {SHORT_DESCRIPTION} characters", MAX_VALUES, SHORT_DESCRIPTION),
        ("descriptions removed", MAX_VALUES, 0),
    ]
    truncation: list[str] = []
    text = ""
    for label, max_values, desc_len in steps:
        text = _render(registry, now, max_values, desc_len)
        if label != "full":
            truncation.append(label)
        if len(text) <= budget_chars:
            return PromptView(text, truncation)
    truncation.append(f"still over budget ({len(text)} > {budget_chars} characters)")
    return PromptView(text, truncation)


def first_messages(view: PromptView, question: str) -> list[ChatMessage]:
    return [
        ChatMessage(role="system", content=f"{SYSTEM_PROMPT}\n{view.text}"),
        ChatMessage(role="user", content=question),
    ]


def retry_messages(
    previous: list[ChatMessage], answer: str, issues: list[Issue], parse_error: str | None
) -> list[ChatMessage]:
    if parse_error is not None:
        feedback = f"Your answer was not a valid intent: {parse_error}"
    else:
        listed = "\n".join(f"- {i.code} at {i.location}: {i.message}" for i in issues)
        feedback = f"Your intent failed validation:\n{listed}"
    return [
        *previous,
        ChatMessage(role="assistant", content=answer),
        ChatMessage(
            role="user",
            content=f"{feedback}\nReturn a corrected intent, or unanswerable with a reason.",
        ),
    ]
