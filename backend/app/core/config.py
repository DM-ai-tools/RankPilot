"""Application settings — all secrets from environment (Railway vault in prod)."""

from functools import lru_cache

from pydantic import AliasChoices, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Used when JWT_SECRET_KEY is unset or a weak placeholder (local dev only).
_DEV_JWT_SECRET = (
    "rankpilot-local-dev-only-not-for-production-minimum-thirty-two-chars"
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "RankPilot API"
    debug: bool = False
    api_v1_prefix: str = "/api/v1"

    # Comma-separated browser origins for SPA (Vite default + 127.0.0.1).
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    database_url: str = "postgresql+asyncpg://rankpilot:rankpilot@localhost:5432/rankpilot"
    redis_url: str = "redis://localhost:6379/0"

    jwt_secret_key: str = ""
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60

    @model_validator(mode="after")
    def _database_must_be_postgresql(self) -> "Settings":
        """RankPilot SEO data layer is PostgreSQL only (see infra/sql). No SQLite/MySQL."""
        u = (self.database_url or "").strip().lower()
        if not u.startswith("postgresql+asyncpg://"):
            raise ValueError(
                "DATABASE_URL must be PostgreSQL with asyncpg, e.g. "
                "postgresql+asyncpg://postgres:PASSWORD@localhost:5432/rankpilot "
                "(encode @ in password as %40). Apply migrations: backend/scripts/apply_migrations.py"
            )
        return self

    @model_validator(mode="after")
    def _jwt_secret_dev_fallback(self) -> "Settings":
        key = (self.jwt_secret_key or "").strip()
        weak = {
            "",
            "change-me",
            "change-me-in-production",
            "change-me-to-a-long-random-string",
        }
        if key in weak or len(key) < 32:
            object.__setattr__(self, "jwt_secret_key", _DEV_JWT_SECRET)
        return self

    # --- L2 AI (content, chat, reports) ---
    anthropic_api_key: str = ""
    anthropic_content_model: str = ""  # optional; default Sonnet 4.6 in content_generation_service
    openai_api_key: str = ""

    # --- L1 SERP / ranks (DataForSEO HTTP Basic — accept common .env spellings) ---
    dataforseo_login: str = Field(
        default="",
        validation_alias=AliasChoices("DATAFORSEO_LOGIN", "DATAFORSEO_API_LOGIN", "DATAFORSEO_USER"),
    )
    dataforseo_password: str = Field(
        default="",
        validation_alias=AliasChoices(
            "DATAFORSEO_PASSWORD",
            "DATAFORSEO_API_PASSWORD",
            "DATAFORSEO_SECRET",
        ),
    )

    # --- Google (GBP, GSC, GA4, PageSpeed, Rich Results, KG) ---
    google_client_id: str = ""
    google_client_secret: str = ""
    # Base URL where Google OAuth callback is reachable (no trailing slash)
    # Local dev: http://localhost:8000  |  Prod: https://api.yourdomain.com
    google_redirect_base_url: str = "http://localhost:8000"
    google_places_api_key: str = ""
    google_pagespeed_key: str = ""
    google_kg_api_key: str = ""
    google_rich_results_key: str = ""

    # --- L3 actions ---
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""
    sendgrid_api_key: str = ""
    sendgrid_from_email: str = ""
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_from: str = ""

    # --- L1 citations scraping ---
    # Primary: Firecrawl API key. Backward compatibility accepts BRIGHT_DATA_API_TOKEN too.
    firecrawl_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("FIRECRAWL_API_KEY", "BRIGHT_DATA_API_TOKEN"),
    )

    # --- Auth (production; optional at MVP) ---
    clerk_secret_key: str = ""
    clerk_publishable_key: str = ""

    # --- Integrations ---
    rankpilot_webhook_secret: str = ""

    # --- Observability ---
    sentry_dsn: str = ""
    posthog_key: str = ""
    betterstack_token: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
