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

    # Model ids come from config only. Chosen by ADR-004's rule (Amendment 2): the
    # cheapest model not clearly worse than the best on the fieldservice benchmark,
    # and the best eligible model from another vendor.
    default_model: str | None = "mistralai/mistral-small-24b-instruct-2501"
    second_model: str | None = "google/gemma-4-26b-a4b-it"

    llm_mode: LLMMode = "replay"
    replay_dir: str = "evals/recordings"
    pending_dir: str = "evals/pending"
    # Hard budget for one live `ask` (all its calls), USD.
    ask_budget_usd: float = 0.05
    # The interpret prompt's registry view is truncated deterministically past this size.
    prompt_budget_chars: int = 16000
    max_tokens: int = 1024

    # The hosted beta. Invite codes, comma-separated; when unset, there is no gate.
    invite_codes: SecretStr | None = None
    # A cap on all live model spend per UTC day, kept in `spend_db` across restarts.
    # Unset means no daily cap (each ask still has `ask_budget_usd`).
    daily_spend_cap_usd: float | None = None
    spend_db: str = "data/spend.sqlite"
    # The kill switch: no live model calls at all; asks get a plain message.
    live_answers_off: bool = False

    # Uploaded workspaces, one folder each (see ledgerline/workspace/store.py).
    workspace_dir: str = "data/workspaces"
    # Read the client address from X-Forwarded-For. Set it only behind a proxy that
    # writes that header; otherwise any client could claim any address.
    trust_proxy: bool = False

    @field_validator("now")
    @classmethod
    def _require_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
