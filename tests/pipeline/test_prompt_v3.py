"""interpret-v3: the instructions describe each grammar feature that is switched on,
with its example, and name each one that is off as out of reach."""

from __future__ import annotations

import pytest

from askwell.core.features import ALL
from askwell.core.registry import load_registry
from askwell.pipeline.prompt import EXAMPLES, registry_view, system_message, system_prompt
from tests.core.conftest import FIELDSERVICE_REGISTRY, NOW

MARKERS = {
    "computed": '"op": "multiply"|"subtract"|',
    "durations": '{"days_between": [<date field>',
    "has": '{"has": <entity>',
    "vs_aggregate": '"value": {"of": "avg"|"min"|"max"}',
}


@pytest.mark.parametrize("feature", sorted(MARKERS))
def test_a_feature_is_described_only_when_on(feature: str) -> None:
    on, off = system_prompt(ALL), system_prompt(ALL - {feature})
    assert MARKERS[feature] in on
    assert MARKERS[feature] not in off
    for example_feature, question, _ in EXAMPLES:
        if example_feature == feature:
            assert question in on
            assert question not in off


def test_the_general_rules_are_always_there() -> None:
    for prompt in (system_prompt(ALL), system_prompt(frozenset())):
        assert "Never add a filter the question does not state." in prompt
        assert "A named span of whole months" in prompt
        assert "window functions" in prompt
        assert "set operations" in prompt


def test_the_message_uses_the_views_switches() -> None:
    registry = load_registry(FIELDSERVICE_REGISTRY)
    off = ALL - {"has"}
    message = system_message(registry_view(registry, NOW, 16000, features=off))
    assert message.startswith(system_prompt(off))
    assert MARKERS["has"] not in message
