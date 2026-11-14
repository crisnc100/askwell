"""Feature switches (v0.3): ASKWELL_FEATURES_OFF names the features to turn off; an
unknown name stops startup rather than silently leaving a feature on."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from askwell.config import Settings
from askwell.core.features import ALL, FEATURES, parse_off
from askwell.workspace.ask import _GENERAL, explain


def test_every_feature_is_on_by_default() -> None:
    assert Settings(_env_file=None).features == ALL  # pyright: ignore[reportCallIssue]
    assert {"link_roles", "inferred_links", "numeric_text"} == FEATURES


def test_named_features_turn_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ASKWELL_FEATURES_OFF", " link_roles , numeric_text,")
    assert Settings(_env_file=None).features == {"inferred_links"}  # pyright: ignore[reportCallIssue]


def test_an_unknown_feature_name_fails_at_startup(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ASKWELL_FEATURES_OFF", "link_role")
    with pytest.raises(ValidationError, match="unknown features"):
        Settings(_env_file=None)  # pyright: ignore[reportCallIssue]
    with pytest.raises(ValueError, match="link_role"):
        parse_off("link_role")


def test_unknown_link_has_plain_text() -> None:
    result = {
        "refusal": "the intent failed validation twice",
        "intent": {"intent_type": "row_list"},
        "validation": {
            "ok": False,
            "attempts": [{"issues": [{"code": "unknown_link", "message": "m"}]}],
        },
    }
    explanation = explain(result)
    assert explanation is not None
    assert explanation["message"] != _GENERAL[0]
    assert "unknown_link" not in explanation["message"] + explanation["suggestion"]
