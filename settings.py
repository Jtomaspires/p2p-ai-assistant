"""Central application configuration loaded from environment variables."""

from typing import Any

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings and feature flags for the P2P workflow."""

    # Infrastructure
    DATABASE_URL: str = "postgresql+psycopg2://p2p:p2p_dev@localhost:5433/p2p"
    REDIS_URL: str = "redis://localhost:6379/0"

    # Workflow
    CONFIDENCE_THRESHOLD: float = 0.7
    NEAR_DUE_DAYS: int = 7
    VAT_RATE: float = 0.23
    MATCH_VALUE_TOLERANCE_PCT: float = 0.02
    MATCH_VALUE_TOLERANCE_ABS: float = 1.00

    # Routing
    DEFAULT_OPERATOR_ID: str = "op_joao"

    # Mailboxes
    INVOICING_EMAIL: str = "invoicing@company.com"
    PAYMENTS_EMAIL: str = "payments@company.com"

    # LLM
    LLM_PRIMARY_MODEL: str = "gpt-4o-mini"
    LLM_PRIMARY_API_KEY: str | None = None
    LLM_PRIMARY_BASE_URL: str | None = None
    LLM_FALLBACK_MODEL: str | None = None
    LLM_FALLBACK_API_KEY: str | None = None
    LLM_FALLBACK_BASE_URL: str | None = None
    LLM_TIMEOUT_S: int = 15
    LLM_RETRY_BACKOFF_S: int = 2

    # Feature flags (safe development defaults)
    NYLAS_SEND_ENABLED: bool = False
    SPF_DKIM_ENABLED: bool = False
    SECURITY_CHECK_ENABLED: bool = False
    SENDER_DOMAIN_WHITELIST: str = (
        "acme-supplies.com,group-subsidiary.com,p2p-branch.com,company.com"
    )
    TRIAGE_DISCARD_MIN_CONFIDENCE: float = 0.8
    INTENT_MIN_CONFIDENCE: float = 0.5

    @field_validator(
        "LLM_PRIMARY_API_KEY",
        "LLM_PRIMARY_BASE_URL",
        "LLM_FALLBACK_MODEL",
        "LLM_FALLBACK_API_KEY",
        "LLM_FALLBACK_BASE_URL",
        mode="before",
    )
    @classmethod
    def empty_or_placeholder_llm_setting_is_none(cls, value: Any) -> Any:
        """Ignore empty values and documentation placeholders from .env files."""
        if not isinstance(value, str):
            return value
        stripped = value.strip()
        if not stripped or (stripped.startswith("<") and stripped.endswith(">")):
            return None
        return stripped

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
