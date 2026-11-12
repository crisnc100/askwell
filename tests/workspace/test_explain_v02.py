"""G9: every validator code added in v0.2 has its own plain-English message and
suggestion on the Ask page, never the general fallback and never the code itself."""

from __future__ import annotations

import pytest

from askwell.workspace.ask import _GENERAL, explain

NEW_CODES = ["placeholder_reason", "ratio_ref", "ratio_shape", "series_shape", "series_date_field"]


@pytest.mark.parametrize("code", NEW_CODES)
def test_every_new_code_has_plain_text(code: str) -> None:
    result = {
        "refusal": "the intent failed validation twice",
        "intent": {"intent_type": "summary"},
        "validation": {"ok": False, "attempts": [{"issues": [{"code": code, "message": "m"}]}]},
    }
    explanation = explain(result)
    assert explanation is not None
    assert explanation["message"] != _GENERAL[0]
    assert explanation["suggestion"]
    assert code not in explanation["message"] + explanation["suggestion"]


def test_the_new_codes_are_the_validators_codes() -> None:
    from typing import get_args

    from askwell.core.validate import ErrorCode

    assert set(NEW_CODES) <= set(get_args(ErrorCode))
