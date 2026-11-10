"""Runtime configuration. Every value can be set from the environment or `.env`."""

from __future__ import annotations

from datetime import UTC, datetime
from functools import lru_cache
from typing import Literal

from pydantic import AliasChoices, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_NOW = datetime(2026, 6, 30, tzinfo=UTC)

# replay: recordings only. export: recordings, and every unrecorded request is written
# to the pending directory for a simulated answer (no API key needed; see
# docs/rerecord.md). record / live: OpenRouter, budget-guarded.
LLMMode = Literal["record", "replay", "live", "export"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="LEDGERLINE_",
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
        "postgresql+psycopg://ledgerline_owner:ledgerline@localhost:56432/ledgerline"
    )
    # Read-only role (SELECT only): everything that answers questions uses this.
    database_ro_url: str = (
        # Local compose dev credential (audited in .secrets.baseline).
        "postgresql+psycopg://ledgerline_ro:ledgerline_ro@localhost:56432/ledgerline"
    )

    # The app DB: Ledgerline's own tables (the ask_log audit), never the data DB.
    # Local compose dev credential (audited in .secrets.baseline).
    app_database_url: str = (
        "postgresql+psycopg://ledgerline_owner:ledgerline@localhost:56432/ledgerline_app"
    )
    row_cap: int = 1000
    query_timeout_s: float = 5.0

    openrouter_api_key: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices("OPENROUTER_API_KEY", "LEDGERLINE_OPENROUTER_API_KEY"),
    )
    openrouter_base_url: str = "https://openrouter.ai/api/v1"

    # Model ids come from config only. The real spike (ADR-004) is deferred until a key
    # exists; this provisional target is what simulated answers stand in for.
    default_model: str | None = "openai/gpt-oss-120b"
    second_model: str | None = None

    llm_mode: LLMMode = "replay"
    replay_dir: str = "evals/recordings"
    pending_dir: str = "evals/pending"
    # Hard budget for one live `ask` (all its calls), USD.
    ask_budget_usd: float = 0.05
    # The interpret prompt's registry view is truncated deterministically past this size.
    prompt_budget_chars: int = 16000
    max_tokens: int = 1024

    @field_validator("now")
    @classmethod
    def _require_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
