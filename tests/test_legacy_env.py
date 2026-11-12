"""Settings under the pre-rename LEDGERLINE_ names still apply for one release."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from askwell.config import Settings


@pytest.fixture(autouse=True)
def _clean(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # Away from the repository's .env, so only what each test sets is read.
    monkeypatch.chdir(tmp_path)
    for name in ("ROW_CAP", "INVITE_CODES", "ANTHROPIC_API_KEY"):
        monkeypatch.delenv(f"ASKWELL_{name}", raising=False)
        monkeypatch.delenv(f"LEDGERLINE_{name}", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)


def test_an_old_name_applies_with_a_warning(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setenv("LEDGERLINE_ROW_CAP", "7")
    with caplog.at_level(logging.WARNING, logger="askwell.config"):
        settings = Settings()
    assert settings.row_cap == 7
    assert "LEDGERLINE_ROW_CAP -> ASKWELL_ROW_CAP" in caplog.text


def test_the_new_name_wins_over_the_old(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LEDGERLINE_ROW_CAP", "7")
    monkeypatch.setenv("ASKWELL_ROW_CAP", "9")
    assert Settings().row_cap == 9


def test_an_old_name_in_the_env_file_applies(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("LEDGERLINE_INVITE_CODES=abc,def\n", encoding="utf-8")
    codes = Settings().invite_codes
    assert codes is not None
    assert codes.get_secret_value() == "abc,def"


def test_an_old_alias_applies(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LEDGERLINE_ANTHROPIC_API_KEY", "sk-old")
    key = Settings().anthropic_api_key
    assert key is not None
    assert key.get_secret_value() == "sk-old"


def test_no_old_names_no_warning(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING, logger="askwell.config"):
        Settings()
    assert "LEDGERLINE_" not in caplog.text
