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

    # When false (default), first boot runs scripts/apply_migrations.py if rp_jobs is missing (no Railway Shell).
    skip_auto_sql_migrate: bool = Field(
        default=False,
        validation_alias=AliasChoices("RANKPILOT_SKIP_AUTO_MIGRATE"),
    )

    jwt_secret_key: str = ""
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60

    @model_validator(mode="after")
    def _database_must_be_postgresql(self) -> "Settings":
        """RankPilot SEO data layer is PostgreSQL only (see infra/sql). No SQLite/MySQL.

        Railway (and many PaaS) supplies DATABASE_URL as ``postgresql://`` or
        ``postgres://``; we transparently upgrade either to the asyncpg scheme.
        """
        u = (self.database_url or "").strip()
        # Normalise Railway / Heroku / Supabase URL formats to asyncpg scheme.
        for old_prefix in ("postgres://", "postgresql://"):
            if u.startswith(old_prefix):
                u = "postgresql+asyncpg://" + u[len(old_prefix):]
                object.__setattr__(self, "database_url", u)
                break
        if not u.lower().startswith("postgresql+asyncpg://"):
            raise ValueError(
                "DATABASE_URL must be PostgreSQL, e.g. "
                "postgresql+asyncpg://postgres:PASSWORD@host:5432/rankpilot "
                "or the plain postgresql:// form (auto-upgraded to asyncpg). "
                "Apply migrations: backend/scripts/apply_migrations.py"
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
    # OpenRouter (Perplexity Sonar) — SEO Website meta + GBP post direction prompts
    openrouter_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("OPENROUTER_API_KEY", "PERPLEXITY_API_KEY"),
    )
    openrouter_model: str = Field(
        default="perplexity/sonar-pro",
        validation_alias=AliasChoices("OPENROUTER_MODEL", "PERPLEXITY_MODEL"),
    )
    openrouter_prompt_model: str = Field(
        default="openai/gpt-4o-mini",
        validation_alias=AliasChoices("OPENROUTER_PROMPT_MODEL", "OPENAI_PROMPT_MODEL"),
    )

    # --- Runway (GBP AI images — Gemini / Nano Banana via Runway API) ---
    runwayml_api_key: str = Field(default="", validation_alias=AliasChoices("RUNWAYML_API_KEY", "RUNWAY_API_KEY"))
    runwayml_base_url: str = Field(
        default="https://api.dev.runwayml.com/v1",
        validation_alias=AliasChoices("RUNWAYML_BASE_URL", "RUNWAY_BASE_URL"),
    )
    runwayml_api_version: str = Field(default="2024-11-06", validation_alias="RUNWAYML_API_VERSION")
    runwayml_model_image: str = Field(
        default="gemini_2.5_flash",
        validation_alias=AliasChoices("RUNWAYML_MODEL_IMAGE", "RUNWAY_MODEL_IMAGE"),
    )
    runwayml_image_size: str = Field(default="1K", validation_alias="RUNWAYML_IMAGE_SIZE")

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

    # --- Ahrefs Keywords Explorer (live volume + KD) ---
    ahrefs_api_key: str = Field(default="", validation_alias=AliasChoices("AHREFS_API_KEY", "AHREFS_TOKEN"))

    # --- Google (GBP, GSC, GA4, PageSpeed, Rich Results, KG) ---
    google_client_id: str = ""
    google_client_secret: str = ""
    # Google Ads API (Keyword Planner) — developer token from Ads UI → Tools → API Center
    google_ads_developer_token: str = Field(
        default="",
        validation_alias=AliasChoices("GOOGLE_ADS_DEVELOPER_TOKEN", "GOOGLE_ADS_API_DEVELOPER_TOKEN"),
    )
    google_ads_login_customer_id: str = Field(
        default="",
        validation_alias=AliasChoices("GOOGLE_ADS_LOGIN_CUSTOMER_ID", "GOOGLE_ADS_MCC_ID"),
    )
    # Base URL where Google OAuth callback is reachable (no trailing slash)
    # Local dev: http://localhost:8000  |  Prod: https://api.yourdomain.com
    google_redirect_base_url: str = "http://localhost:8000"
    # Public URL Google can reach to fetch GBP photos (sourceUrl). Defaults to google_redirect_base_url.
    public_api_base_url: str = Field(
        default="",
        validation_alias=AliasChoices("PUBLIC_API_BASE_URL", "RANKPILOT_PUBLIC_API_URL"),
    )
    # Optional: host GBP photos for Google sourceUrl when running on localhost (free at imgbb.com / freeimage.host)
    imgbb_api_key: str = Field(default="", validation_alias=AliasChoices("IMGBB_API_KEY",))
    freeimage_api_key: str = Field(default="", validation_alias=AliasChoices("FREEIMAGE_API_KEY",))
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


def get_ahrefs_api_key() -> str:
    """Ahrefs key from settings; re-reads .env if cache is stale (e.g. key added without restart)."""
    key = (get_settings().ahrefs_api_key or "").strip()
    if key:
        return key
    get_settings.cache_clear()
    return (get_settings().ahrefs_api_key or "").strip()


def get_openrouter_api_key() -> str:
    """OpenRouter key from settings; re-reads .env if cache is stale."""
    key = (get_settings().openrouter_api_key or "").strip()
    if key:
        return key
    get_settings.cache_clear()
    return (get_settings().openrouter_api_key or "").strip()


def get_openrouter_model() -> str:
    model = (get_settings().openrouter_model or "").strip()
    if model:
        return model
    get_settings.cache_clear()
    return (get_settings().openrouter_model or "perplexity/sonar-pro").strip()


def get_openrouter_prompt_model() -> str:
    model = (get_settings().openrouter_prompt_model or "").strip()
    if model:
        return model if "/" in model else f"openai/{model}"
    get_settings.cache_clear()
    raw = (get_settings().openrouter_prompt_model or "openai/gpt-4o-mini").strip()
    return raw if "/" in raw else f"openai/{raw}"


def get_openai_api_key() -> str:
    key = (get_settings().openai_api_key or "").strip()
    if key:
        return key
    get_settings.cache_clear()
    return (get_settings().openai_api_key or "").strip()
