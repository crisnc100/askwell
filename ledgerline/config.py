"""Runtime configuration. Every value can be set from the environment or `.env`."""

from __future__ import annotations

from datetime import UTC, datetime
from functools import lru_cache
from typing import Literal

from pydantic import AliasChoices, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_NOW = datetime(2026, 6, 30, tzinfo=UTC)

LLMMode = Literal["record", "replay", "live"]


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

    # Model ids come from config only. Unset until the model spike picks them (ADR-004).
    default_model: str | None = None
    second_model: str | None = None

    llm_mode: LLMMode = "replay"
    replay_dir: str = "evals/recordings"
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
