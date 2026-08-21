"""Central application configuration loaded from environment variables."""

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
    LLM_TIMEOUT_S: int = 15
    LLM_RETRY_BACKOFF_S: int = 2

    # Feature flags (safe development defaults)
    NYLAS_SEND_ENABLED: bool = False
    SPF_DKIM_ENABLED: bool = False
    SECURITY_CHECK_ENABLED: bool = False

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
