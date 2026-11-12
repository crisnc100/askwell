"""Runtime configuration. Every value can be set from the environment or `.env`."""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from dotenv import dotenv_values
from pydantic import AliasChoices, Field, SecretStr, field_validator
from pydantic.fields import FieldInfo
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)

DEFAULT_NOW = datetime(2026, 6, 30, tzinfo=UTC)

# replay: recordings only. export: recordings, and every unrecorded request is written
# to the pending directory for a simulated answer (no API key needed; see
# docs/rerecord.md). record / live: a live provider (OpenRouter or Anthropic), budget-guarded.
LLMMode = Literal["record", "replay", "live", "export"]

PREFIX = "ASKWELL_"
# The product was called Ledgerline. Its variable names still work for one release, so a
# deployed .env keeps running; remove this fallback in the release after 0.2.0.
LEGACY_PREFIX = "LEDGERLINE_"

log = logging.getLogger(__name__)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix=PREFIX,
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # The single reference time for the seeder and for relative-date resolution.
    # Gold results are computed against it.
    now: datetime = DEFAULT_NOW

    # Owner role: creates and seeds the fieldservice schema.
    database_url: str = (
        # Local compose dev credential (audited in .secrets.baseline).
        "postgresql+psycopg://askwell_owner:askwell@localhost:56432/askwell"
    )
    # Read-only role (SELECT only): everything that answers questions uses this.
    database_ro_url: str = (
        # Local compose dev credential (audited in .secrets.baseline).
        "postgresql+psycopg://askwell_ro:askwell_ro@localhost:56432/askwell"
    )

    # The app DB: Askwell's own tables (the ask_log audit), never the data DB.
    # Local compose dev credential (audited in .secrets.baseline).
    app_database_url: str = "postgresql+psycopg://askwell_owner:askwell@localhost:56432/askwell_app"
    row_cap: int = 1000
    query_timeout_s: float = 5.0

    openrouter_api_key: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices("OPENROUTER_API_KEY", "ASKWELL_OPENROUTER_API_KEY"),
    )
    openrouter_base_url: str = "https://openrouter.ai/api/v1"

    # Model names come from config only; `anthropic:<id>` goes to the Anthropic API,
    # anything else to OpenRouter (askwell/llm/providers.py). The default is
    # Cristian's choice, measured under ADR-004's gates (Amendment 3); the second is the
    # best eligible model from another vendor (Amendment 2).
    default_model: str | None = "anthropic:claude-haiku-5-5"
    second_model: str | None = "google/gemma-4-26b-a4b-it"

    # The direct Anthropic API, for models configured as `anthropic:<model id>`
    # (askwell/llm/providers.py). Every other model goes through OpenRouter.
    anthropic_api_key: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices("ANTHROPIC_API_KEY", "ASKWELL_ANTHROPIC_API_KEY"),
    )
    anthropic_base_url: str | None = None
    # How much the model thinks before answering. A short structured form needs little.
    anthropic_effort: Literal["low", "medium", "high"] = "low"
    # USD per million tokens. Haiku 5.5's price for prompts up to 100,000 tokens; ours are
    # far smaller. The daily cap and per-ask budgets charge at these prices.
    anthropic_input_usd_per_mtok: float = Field(
        default=0.10,
        validation_alias=AliasChoices(
            "ANTHROPIC_INPUT_USD_PER_MTOK", "ASKWELL_ANTHROPIC_INPUT_USD_PER_MTOK"
        ),
    )
    anthropic_output_usd_per_mtok: float = Field(
        default=0.50,
        validation_alias=AliasChoices(
            "ANTHROPIC_OUTPUT_USD_PER_MTOK", "ASKWELL_ANTHROPIC_OUTPUT_USD_PER_MTOK"
        ),
    )

    llm_mode: LLMMode = "replay"
    replay_dir: str = "evals/recordings"
    pending_dir: str = "evals/pending"
    # Hard budget for one live `ask` (all its calls), USD.
    ask_budget_usd: float = 0.05
    # The interpret prompt's registry view is truncated deterministically past this size.
    prompt_budget_chars: int = 16000
    max_tokens: int = 1024

    # Where this runs. In "beta" or "prod" the app refuses to start without invite codes,
    # so a missing setting can never open the hosted beta to everyone.
    env: Literal["dev", "beta", "prod"] = "dev"
    # The hosted beta. Invite codes, comma-separated; when unset, there is no gate.
    invite_codes: SecretStr | None = None
    # A cap on all live model spend per UTC day, kept in `spend_db` across restarts.
    # Unset means no daily cap (each ask still has `ask_budget_usd`).
    daily_spend_cap_usd: float | None = None
    spend_db: str = "data/spend.sqlite"
    # The kill switch: no live model calls at all; asks get a plain message.
    live_answers_off: bool = False

    # Uploaded workspaces, one folder each (see askwell/workspace/store.py).
    workspace_dir: str = "data/workspaces"
    # Read the client address from X-Forwarded-For. Set it only behind a proxy that
    # writes that header; otherwise any client could claim any address.
    trust_proxy: bool = False

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        # Earlier sources win, so an ASKWELL_ name always beats its LEDGERLINE_ twin.
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            LegacyNamesSource(settings_cls),
            file_secret_settings,
        )

    @field_validator("now")
    @classmethod
    def _require_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)


class LegacyNamesSource(PydanticBaseSettingsSource):
    """Values set under the old LEDGERLINE_ names, from the environment or `.env`, with a
    warning naming each one to rename."""

    def get_field_value(self, field: FieldInfo, field_name: str) -> tuple[Any, str, bool]:
        # Unused: __call__ reads every name at once.
        return None, field_name, False

    def __call__(self) -> dict[str, Any]:
        found: dict[str, str] = {}
        env_file = self.config.get("env_file")
        if isinstance(env_file, str) and Path(env_file).is_file():
            for key, value in dotenv_values(env_file).items():
                if value is not None:
                    found[key.upper()] = value
        found.update({key.upper(): value for key, value in os.environ.items()})

        values: dict[str, Any] = {}
        used: list[str] = []
        for field_name, field in self.settings_cls.model_fields.items():
            # A field with aliases is read under each ASKWELL_ alias; others under the prefix.
            alias = field.validation_alias
            if isinstance(alias, AliasChoices):
                names = [
                    (str(choice), str(choice))
                    for choice in alias.choices
                    if str(choice).startswith(PREFIX)
                ]
            else:
                names = [(PREFIX + field_name.upper(), field_name)]
            for new_name, key in names:
                old_name = LEGACY_PREFIX + new_name.removeprefix(PREFIX)
                if old_name in found:
                    values.setdefault(key, found[old_name])
                    used.append(f"{old_name} -> {new_name}")
        if used:
            log.warning(
                "Deprecated LEDGERLINE_ settings are still read for this release; rename them: %s",
                ", ".join(used),
            )
        return values


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
