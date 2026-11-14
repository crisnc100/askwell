"""The interpret prompt: instructions plus a compact registry view.

The view lists entities, fields and relationships in registry order. Hidden fields are
never in it. When it is over budget, truncation is deterministic: allowed values past 20
per field go first, then descriptions shorten (60 characters, then none). Every step
taken is returned so the caller can log it.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from askwell.core.features import ALL, Features
from askwell.core.registry import FieldDef, Registry, enabled_links
from askwell.core.validate import Issue
from askwell.llm.types import ChatMessage

PROMPT_VERSION = "interpret-v3"
MAX_VALUES = 20
SHORT_DESCRIPTION = 60

# Worked examples on a made-up schema (tickets and agents), so the prompt teaches the
# grammar without naming any real schema's tables. Each is shown only when the feature
# it uses (or None: always) is switched on. A test validates each one.
EXAMPLES: list[tuple[str | None, str, dict[str, Any]]] = [
    (
        None,
        "What percentage of tickets were escalated?",
        {
            "intent_type": "summary",
            "entity": "tickets",
            "metrics": [
                {
                    "agg": "count",
                    "alias": "escalated",
                    "where": [{"field": "stage", "op": "eq", "value": "escalated"}],
                },
                {"agg": "count", "alias": "total"},
                {
                    "agg": "ratio",
                    "alias": "pct_escalated",
                    "numerator": "escalated",
                    "denominator": "total",
                    "as_percent": True,
                },
            ],
        },
    ),
    (
        None,
        "Tickets opened and tickets closed per week this quarter",
        {
            "intent_type": "date_series",
            "entity": "tickets",
            "grain": "iso_week",
            "date_range": {"relative": "this_quarter"},
            "series": [
                {"metric": {"agg": "count"}, "date_field": "opened_on", "alias": "opened"},
                {"metric": {"agg": "count"}, "date_field": "closed_on", "alias": "closed"},
            ],
        },
    ),
    (
        "durations",
        "Mean days from a ticket being opened to it being closed, by stage?",
        {
            "intent_type": "grouped_summary",
            "entity": "tickets",
            "metrics": [
                {
                    "agg": "avg",
                    "alias": "avg_days",
                    "field": {"days_between": ["opened_on", "closed_on"]},
                }
            ],
            "group_by": [{"field": "stage"}],
        },
    ),
    (
        "computed",
        "What did each team bill, minutes times the agent's rate?",
        {
            "intent_type": "grouped_summary",
            "entity": "tickets",
            "metrics": [
                {
                    "agg": "sum",
                    "alias": "billed",
                    "field": {"op": "multiply", "left": "minutes", "right": "agents.rate"},
                }
            ],
            "group_by": [{"field": "agents.team"}],
        },
    ),
    (
        "has",
        "Which agents have no escalated tickets?",
        {
            "intent_type": "row_list",
            "entity": "agents",
            "select": ["id", "team"],
            "filters": [
                {
                    "has": "tickets",
                    "none": True,
                    "where": [{"field": "stage", "op": "eq", "value": "escalated"}],
                }
            ],
        },
    ),
    (
        "vs_aggregate",
        "Tickets opened this month that took longer than this month's average",
        {
            "intent_type": "row_list",
            "entity": "tickets",
            "select": ["id", "minutes"],
            "filters": [{"field": "minutes", "op": "gt", "value": {"of": "avg"}}],
            "date_range": {"field": "opened_on", "relative": "this_month"},
        },
    ),
    (
        None,
        "Per agent, count the months that had at least one ticket they closed.",
        {
            "intent_type": "unanswerable",
            "unanswerable_reason": "it needs a distinct count of months, which the intent "
            "cannot express",
        },
    ),
]

_BEFORE_FEATURES = """\
You turn a business question about one database into a structured intent (JSON). You \
never write SQL. Code validates your intent against the registry below and writes the \
query, so use only the entities and fields listed, by their exact names.

How to fill the intent:
- intent_type: "summary" (one row of metrics), "grouped_summary" (metrics per group_by), \
"row_list" (rows of `select` fields), "date_series" (one row per calendar period, one \
column per series), or "unanswerable".
- entity: the base table. Fields on other entities are written "entity.field" and are \
joined for you along the relationships listed; a bare "field" means the base entity.
- metrics: {"agg": count|count_distinct|sum|avg|min|max, "field": ..., "alias": ...}. \
count without a field counts rows. Aliases are lowercase slugs, distinct from group \
labels.
- A metric may have its own "where": [conditions] (same form as filters, no groups). It \
then counts or sums only the rows that match, while other metrics still see every row. \
Use it for "how many of them are X" next to a total.
- A ratio metric divides one metric by another of the same intent: {"agg": "ratio", \
"alias", "numerator": <metric alias>, "denominator": <metric alias>, "as_percent": \
true|false}. Both parts are plain metrics (not ratios). as_percent multiplies by 100. \
Use it for shares, percentages, rates and averages per item. A ratio can be sorted on \
and used in having.
- filters: a list combined with AND. Each item is a condition {"field", "op", ...} or one \
group {"any_of": [conditions]} / {"all_of": [conditions]} (groups do not nest). \
Operators: eq, neq, gt, gte, lt, lte take "value" (or "other_field" to compare two \
fields); between takes "values": [low, high]; in takes "values": [...]; is_null takes \
"value": true (IS NULL) or false (IS NOT NULL); ilike_contains takes a text "value". \
Categorical fields list their allowed values: use one of them. Never add a filter the \
question does not state.
- date_range: {"field": <a date field>, "relative": <token>} with tokens today, \
yesterday, last_n_days, last_n_weeks, last_n_months (these three need "n"), this_week, \
last_week, this_month, last_month, this_quarter, last_quarter, this_year, ytd, \
last_year; or {"field", "start", "end"} as ISO dates, end exclusive. A named span of \
whole months ("in March", "from March to May") takes "start" and "end": the first day \
of its first month and the first day after its last month. Do not compute dates for \
the relative tokens and do not also filter that field.
- group_by: [{"field", "grain"}]; grain (day, iso_week, month, quarter, year) only on \
date fields. A grouped label is the field name (or "entity__field" for joined fields), \
plus "_<grain>" when a grain is set.
- having: [{"metric": <metric alias>, "op", "value" or "values"}], only with group_by.
- order_by: [{"target": <metric alias, group label or field>, "direction": asc|desc}]; \
limit: a positive integer.
- date_series: for two or more things counted by different dates in one table (for \
example, created per month next to finished per month). It takes "entity", "grain", \
optional "filters" shared by every series, an optional "date_range" with no "field" \
(it applies to each series by its own date), and "series": 1 to 4 items of \
{"metric": {"agg", "field"}, "date_field": <a date field>, "where": [conditions], \
"alias"}. The first column is "period". No metrics, select, group_by, having, order_by \
or limit.
"""

# What each switchable feature adds to "How to fill the intent", and what the prompt
# says is out of reach when it is switched off.
_FEATURE_TEXT: dict[str, tuple[str, str]] = {
    "computed": (
        """\
- A value computed from two numeric fields, row by row: {"op": "multiply"|"subtract"|\
"add", "left": <field>, "right": <field>, "alias"}. It goes wherever a field goes in \
metrics, select and filters (quantity times price, price minus cost). Exactly two \
fields; it does not nest. A selected one is sorted by its alias.
""",
        "a product of two fields (such as quantity times price)",
    ),
    "durations": (
        """\
- Days between two dates, with fractions: {"days_between": [<date field>, <date field \
or "now">], "alias"}; "now" is the reference date. It goes wherever a numeric field \
goes (average days to close, how long each item has been open).
""",
        "a duration between two dates",
    ),
    "has": (
        """\
- A related-rows filter, in filters: {"has": <entity>, "where": [conditions], "none": \
true|false}. It keeps the base rows that have (with "none": true, that have no) rows of \
that entity leading to them, directly or along a chain of links. "where" narrows which \
related rows count; its fields are read from that entity. When two links lead back, \
name one as "entity@link".
""",
        '"has none" questions (items with no related rows)',
    ),
    "vs_aggregate": (
        """\
- To compare a numeric field of the base entity with its own average, minimum or \
maximum: {"field", "op": eq|neq|gt|gte|lt|lte, "value": {"of": "avg"|"min"|"max"}}, as \
a top-level filter of a summary or row_list. The aggregate is taken over the rows the \
question selects (its other filters and date range, which must all be on the base \
entity). When the question compares with a different set of rows ("this year's jobs \
longer than last year's average"), it is unanswerable.
""",
        "comparison with an average or other aggregate",
    ),
}

_ALWAYS_OUT = (
    "set operations (in both of two lists, in one but not the other), comparison with the "
    "top row's value, a distinct count of periods, and window functions (running totals, "
    "ranks within groups)"
)


def system_prompt(features: Features = ALL) -> str:
    """The instructions, describing each switched-on feature and naming every other one
    as out of reach."""
    described = "".join(text for name, (text, _) in _FEATURE_TEXT.items() if name in features)
    off = [out for name, (_, out) in _FEATURE_TEXT.items() if name not in features]
    out_of_reach = ", ".join([*off, _ALWAYS_OUT])
    examples = "".join(
        f"Q: {q}\nA: {json.dumps(intent)}\n"
        for feature, q, intent in EXAMPLES
        if feature is None or feature in features
    )
    return (
        _BEFORE_FEATURES
        + described
        + """\
- unanswerable_reason: only for "unanswerable", and it must say what is missing. Leave \
it out of every other intent.

Refuse first. When a question needs something this intent cannot express, answer \
"unanswerable" and name what is missing, rather than answer a nearby question. Still \
out of reach: """
        + out_of_reach
        + """\
. Also answer "unanswerable" when the data is not in the registry, when the question \
needs a field that is not listed (some fields are deliberately hidden), or when it asks \
to change data (insert, update, delete, drop). Never guess a field or a value that is \
not listed.

Examples, on a made-up schema (tickets with opened_on, closed_on, stage and minutes; \
agents with team and rate):
"""
        + examples
    )


SYSTEM_PROMPT = system_prompt(ALL)


@dataclass
class PromptView:
    text: str
    truncation: list[str] = field(default_factory=list[str])
    # The switches the view was rendered for; the instructions describe the same ones.
    features: Features = ALL


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


def _render(
    registry: Registry,
    now: datetime,
    max_values: int | None,
    desc_len: int | None,
    time_zone: str,
    features: Features = ALL,
) -> str:
    registry = enabled_links(registry, features)
    lines = [f"Reference date: {now.date().isoformat()} ({time_zone}).", "", "Entities:"]
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
    # A relationship whose key field is hidden is left out: listing it would name the
    # hidden field. (The validator still uses it for joins.)
    shown = [
        rel
        for rel in registry.relationships
        if not registry.entities[rel.from_entity].fields[rel.from_field].hidden
        and not registry.entities[rel.to_entity].fields[rel.to_field].hidden
    ]
    if shown:
        lines += ["", "Relationships (many-to-one; joins follow them):"]
        for rel in shown:
            lines.append(f"- {rel.from_entity}.{rel.from_field} -> {rel.to_entity}.{rel.to_field}")
    pairs = Counter((rel.from_entity, rel.to_entity) for rel in shown)
    doubled = [rel for rel in shown if pairs[(rel.from_entity, rel.to_entity)] > 1]
    # Written only for a schema that has such links, so every other prompt is unchanged.
    if doubled and "link_roles" in features:
        lines += [
            "",
            "Named links: these entities are linked in more than one way. A field across one "
            "of them names the link, as entity@link.field, where link is the linking field:",
        ]
        for rel in doubled:
            lines.append(
                f"- {rel.to_entity}@{rel.from_field}.<field>: through "
                f"{rel.from_entity}.{rel.from_field}"
            )
    return "\n".join(lines) + "\n"


def registry_view(
    registry: Registry,
    now: datetime,
    budget_chars: int,
    time_zone: str = "UTC",
    features: Features = ALL,
) -> PromptView:
    """The registry part of the interpret prompt. The Confirm page's preview calls this
    same function, so it shows exactly what the model is sent."""
    steps: list[tuple[str, int | None, int | None]] = [
        ("full", None, None),
        (f"allowed values cut to {MAX_VALUES} per field", MAX_VALUES, None),
        (f"descriptions cut to {SHORT_DESCRIPTION} characters", MAX_VALUES, SHORT_DESCRIPTION),
        ("descriptions removed", MAX_VALUES, 0),
    ]
    truncation: list[str] = []
    text = ""
    for label, max_values, desc_len in steps:
        text = _render(registry, now, max_values, desc_len, time_zone, features)
        if label != "full":
            truncation.append(label)
        if len(text) <= budget_chars:
            return PromptView(text, truncation, features)
    truncation.append(f"still over budget ({len(text)} > {budget_chars} characters)")
    return PromptView(text, truncation, features)


def system_message(view: PromptView) -> str:
    return f"{system_prompt(view.features)}\n{view.text}"


def first_messages(view: PromptView, question: str) -> list[ChatMessage]:
    return [
        ChatMessage(role="system", content=system_message(view)),
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
