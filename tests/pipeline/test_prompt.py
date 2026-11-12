"""The interpret prompt: deterministic, hidden fields never shown, truncation in order."""

from __future__ import annotations

from ledgerline.core.registry import FieldDef, load_registry
from ledgerline.core.validate import Issue
from ledgerline.llm.types import ChatMessage
from ledgerline.pipeline.prompt import (
    MAX_VALUES,
    SYSTEM_PROMPT,
    first_messages,
    registry_view,
    retry_messages,
)
from tests.core.conftest import FIELDSERVICE_REGISTRY, NOW


def test_view_is_deterministic_and_never_shows_hidden_fields() -> None:
    registry = load_registry(FIELDSERVICE_REGISTRY)
    a = registry_view(registry, NOW, 16000)
    b = registry_view(load_registry(FIELDSERVICE_REGISTRY), NOW, 16000)
    assert a.text == b.text
    assert a.truncation == []
    assert "password_hash" not in a.text
    assert "email" not in a.text.replace("Emails and password hashes are hidden", "")
    assert "## users" in a.text
    assert "- username: text" in a.text
    assert "Reference date: 2026-06-30" in a.text
    assert "- invoices.work_order_id -> work_orders.id" in a.text


def test_truncation_drops_values_first_then_descriptions() -> None:
    registry = load_registry(FIELDSERVICE_REGISTRY)
    entities = dict(registry.entities)
    sites = entities["sites"]
    fields = dict(sites.fields)
    many = [f"City{i:03d}" for i in range(120)]
    fields["city"] = FieldDef(
        column="city", type="text", categorical=True, allowed_values=many, description="x" * 200
    )
    entities["sites"] = sites.model_copy(update={"fields": fields})
    big = registry.model_copy(update={"entities": entities})
    full = registry_view(big, NOW, 10**6)
    assert "City119" in full.text
    values_cut = registry_view(big, NOW, len(full.text) - 1)
    assert values_cut.truncation == [f"allowed values cut to {MAX_VALUES} per field"]
    assert "City019" in values_cut.text
    assert "City020" not in values_cut.text
    assert "+100 more" in values_cut.text
    tighter = registry_view(big, NOW, len(values_cut.text) - 1)
    assert tighter.truncation[-1] == "descriptions cut to 60 characters"
    tightest = registry_view(big, NOW, 100)
    assert tightest.truncation[-2] == "descriptions removed"
    assert tightest.truncation[-1].startswith("still over budget")
    assert "Customer segment." not in tightest.text


def test_messages_carry_the_system_prompt_view_and_question() -> None:
    view = registry_view(load_registry(FIELDSERVICE_REGISTRY), NOW, 16000)
    messages = first_messages(view, "How many parts?")
    assert messages[0].role == "system"
    assert messages[0].content.startswith(SYSTEM_PROMPT)
    assert view.text in messages[0].content
    assert messages[1] == ChatMessage(role="user", content="How many parts?")


def test_retry_messages_feed_back_the_typed_errors() -> None:
    first = [ChatMessage(role="system", content="s"), ChatMessage(role="user", content="q")]
    issues = [Issue("unknown_field", "select[0]", "no field 'x' on parts")]
    retry = retry_messages(first, '{"bad": 1}', issues, None)
    assert retry[:2] == first
    assert retry[2] == ChatMessage(role="assistant", content='{"bad": 1}')
    assert "unknown_field at select[0]: no field 'x' on parts" in retry[3].content
    parse = retry_messages(first, "oops", [], "not JSON")
    assert "not a valid intent: not JSON" in parse[3].content


def test_relationships_with_a_hidden_endpoint_are_not_shown() -> None:
    registry = load_registry(FIELDSERVICE_REGISTRY)
    entities = dict(registry.entities)
    invoices = entities["invoices"]
    fields = dict(invoices.fields)
    fields["work_order_id"] = fields["work_order_id"].model_copy(update={"hidden": True})
    entities["invoices"] = invoices.model_copy(update={"fields": fields})
    hidden = registry.model_copy(update={"entities": entities})
    view = registry_view(hidden, NOW, 16000)
    assert "work_order_id" not in view.text.split("Relationships")[1].split("work_order_parts")[0]
    assert "- invoices.work_order_id -> work_orders.id" not in view.text
    assert "- work_orders.site_id -> sites.id" in view.text


# --- interpret-v2 ---


def test_v2_describes_the_new_grammar_and_refuse_first() -> None:
    from ledgerline.pipeline.prompt import PROMPT_VERSION

    assert PROMPT_VERSION == "interpret-v2"
    for phrase in (
        '"where"',
        '"agg": "ratio"',
        '"numerator"',
        '"denominator"',
        '"as_percent"',
        '"date_series"',
        '"date_field"',
        '"grain"',
        "Refuse first",
        "a duration between two dates",
        "a product of two fields",
        '"has none"',
        "a distinct count of periods",
    ):
        assert phrase in SYSTEM_PROMPT, phrase


def test_v2_examples_use_made_up_entities() -> None:
    import re

    registry = load_registry(FIELDSERVICE_REGISTRY)
    examples = set(re.findall(r'"entity": "([a-z_]+)"', SYSTEM_PROMPT))
    assert examples
    assert examples.isdisjoint(registry.entities)
    fields = {name for entity in registry.entities.values() for name in entity.fields}
    named = set(re.findall(r'"(?:field|date_field)": "([a-z_.]+)"', SYSTEM_PROMPT))
    assert named
    assert {n.split(".")[-1] for n in named}.isdisjoint(fields - {"id", "name", "status"})


def test_every_v2_example_validates_against_a_made_up_registry() -> None:
    from ledgerline.core.intent import Intent
    from ledgerline.core.registry import EntityDef, Registry, Relationship
    from ledgerline.core.validate import validate
    from ledgerline.pipeline.prompt import EXAMPLES

    tickets = EntityDef(
        table="tickets",
        fields={
            "id": FieldDef(column="id", type="integer"),
            "agent_id": FieldDef(column="agent_id", type="integer"),
            "opened_on": FieldDef(column="opened_on", type="date"),
            "closed_on": FieldDef(column="closed_on", type="date"),
            "stage": FieldDef(
                column="stage",
                type="text",
                categorical=True,
                allowed_values=["open", "closed", "escalated"],
            ),
            "minutes": FieldDef(column="minutes", type="number", aggregatable=True),
        },
    )
    agents = EntityDef(
        table="agents",
        fields={
            "id": FieldDef(column="id", type="integer"),
            "team": FieldDef(column="team", type="text"),
        },
    )
    registry = Registry(
        schema_version=1,
        draft=False,
        entities={"tickets": tickets, "agents": agents},
        relationships=[
            Relationship(
                from_entity="tickets",
                from_field="agent_id",
                to_entity="agents",
                to_field="id",
                source="declared",
            )
        ],
    )
    assert len(EXAMPLES) >= 3
    for question, example in EXAMPLES:
        result = validate(Intent.model_validate(example), registry, now=NOW)
        assert result.ok, (question, result.issues)
        assert question in SYSTEM_PROMPT
