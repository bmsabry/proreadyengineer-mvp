"""Pydantic settings configuration for the application."""

from typing import List, Optional, Union
from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
import os


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # App
    ENVIRONMENT: str = "development"
    DEBUG: bool = False
    PROJECT_NAME: str = "ProReadyEngineer API"
    FRONTEND_URL: str = os.getenv("FRONTEND_URL", "http://localhost:3000")
    FROM_EMAIL: str = os.getenv("FROM_EMAIL", "info@promechdirectory.com")
    VERSION: str = "0.1.0"
    API_V1_STR: str = "/api/v1"
    SECRET_KEY: str = "change-me-in-production"

    # Database
    POSTGRES_SERVER: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str = "proready_user"
    POSTGRES_PASSWORD: str = "password"
    POSTGRES_DB: str = "proready_engineer"
    DATABASE_URL: Optional[str] = None
    DATABASE_URL_SYNC: Optional[str] = None

    # Redis
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_PASSWORD: Optional[str] = None
    REDIS_URL: str = "redis://localhost:6379/0"

    # Auth
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    ALGORITHM: str = "HS256"

    # AWS
    AWS_ACCESS_KEY_ID: Optional[str] = None
    AWS_SECRET_ACCESS_KEY: Optional[str] = None
    AWS_REGION: str = "us-east-1"
    S3_BUCKET_NAME: str = "proready-engineer-uploads"
    S3_PRESIGNED_URL_EXPIRE_SECONDS: int = 3600

    # Stripe
    STRIPE_SECRET_KEY: Optional[str] = None
    STRIPE_PUBLISHABLE_KEY: Optional[str] = None
    STRIPE_WEBHOOK_SECRET: Optional[str] = None

    # PayPal/Braintree
    PAYPAL_CLIENT_ID: Optional[str] = None
    PAYPAL_CLIENT_SECRET: Optional[str] = None

    # SignRequest
    SIGNWELL_API_KEY: Optional[str] = None
    SIGNWELL_SUBDOMAIN: Optional[str] = None
    SIGNWELL_WEBHOOK_SECRET: Optional[str] = None

    # Email
    EMAIL_PROVIDER: str = "resend"
    RESEND_API_KEY: Optional[str] = None
    SENDGRID_API_KEY: Optional[str] = None
    EMAIL_FROM: str = "info@promechdirectory.com"
    EMAIL_FROM_NAME: str = "ProMechDirectory"
    SMTP_HOST: Optional[str] = None
    SMTP_PORT: int = int(os.getenv('SMTP_PORT', '587'))
    SMTP_USER: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None
    # Admin notification address — receives one email per delivery failure.
    # Defaults to FROM_EMAIL if unset; can be overridden via Admin Settings runtime config.
    ADMIN_EMAIL: Optional[str] = os.getenv('ADMIN_EMAIL', None)
    RESEND_WEBHOOK_SECRET: Optional[str] = None
    SMTP_TLS: bool = True
    SMTP_SSL: bool = False


    # OpenAI
    OPENAI_API_KEY: Optional[str] = None
    OPENAI_API_BASE: Optional[str] = None
    OPENAI_EMBEDDING_MODEL: str = "BAAI/bge-large-en-v1.5"
    OPENAI_LLM_MODEL: str = "gpt-4o-mini"

    # Provider payment options: 1) $1000/yr annual sub 2) $500 one-time profile edit 3) $50/RFQ unlock
    # Search & Quotas (in cents)
    ANONYMOUS_SEARCH_LIMIT_PER_MONTH: int = 0  # anonymous users must register
    REGISTERED_SEARCH_LIMIT_PER_MONTH: int = 5
    SEARCH_TIER_1_LIMIT: int = 100
    SEARCH_TIER_1_PRICE: int = 5000  # $50.00/month
    SEARCH_ANNUAL_PRICE: int = 50000  # $500.00/year (same access as monthly, billed yearly)
    RFQ_UNLOCK_PRICE: int = 5000  # $50.00
    NDA_FEE_PRICE: int = 1000  # $10.00
    # Paid customer search subscribers get this many free NDA-required RFQs per calendar
    # month; beyond it they pay the $10 NDA handling fee.
    NDA_FREE_CREDITS_PER_MONTH: int = 5
    PROVIDER_ANNUAL_SUBSCRIPTION_PRICE: int = 100000  # $1000.00/year
    AD_SUBSCRIPTION_PRICE: int = 5000  # $50.00

    # RFQ Settings
    RFQ_MAX_QUOTES: int = 5
    RFQ_DISPATCH_BATCH_SIZE: int = 5
    RFQ_DISPATCH_BATCH_INTERVAL_HOURS: int = 24

    # Cron job
    CRON_SECRET: Optional[str] = None

    # Security - CORS
    ALLOWED_ORIGINS: str = "http://localhost:3000,http://localhost:3001"
    EXTRA_CORS_ORIGINS: str = ""

    # Security - Email Verification
    REQUIRE_EMAIL_VERIFICATION: bool = True


    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def assemble_db_connection(cls, v: Optional[str], info) -> str:
        """Build async database URL if not provided."""
        if isinstance(v, str) and v:
            # If URL is provided, ensure it uses asyncpg driver
            if v.startswith("postgresql://") and "asyncpg" not in v:
                return v.replace("postgresql://", "postgresql+asyncpg://", 1)
            return v
        # Build from components
        values = info.data
        return (
            f"postgresql+asyncpg://{values.get('POSTGRES_USER')}"
            f":{values.get('POSTGRES_PASSWORD')}@{values.get('POSTGRES_SERVER')}"
            f":{values.get('POSTGRES_PORT')}/{values.get('POSTGRES_DB')}"
        )

    @field_validator("DATABASE_URL_SYNC", mode="before")
    @classmethod
    def assemble_sync_db_connection(cls, v: Optional[str], info) -> str:
        """Build sync database URL for migrations."""
        if isinstance(v, str) and v:
            return v
        values = info.data
        return (
            f"postgresql://{values.get('POSTGRES_USER')}"
            f":{values.get('POSTGRES_PASSWORD')}@{values.get('POSTGRES_SERVER')}"
            f":{values.get('POSTGRES_PORT')}/{values.get('POSTGRES_DB')}"
        )

    @property
    def is_production(self) -> bool:
        """Check if running in production environment."""
        return self.ENVIRONMENT.lower() == "production"

    @property
    def is_development(self) -> bool:
        """Check if running in development environment."""
        return self.ENVIRONMENT.lower() == "development"

    _INSECURE_SECRET_DEFAULT = "change-me-in-production"

    @model_validator(mode="after")
    def _enforce_secret_key(self):
        """Fail fast in production if SECRET_KEY was never overridden.

        A default signing key means anyone can forge JWTs (incl. admin tokens),
        so we refuse to boot in production and warn loudly elsewhere.
        """
        if self.SECRET_KEY == self._INSECURE_SECRET_DEFAULT:
            if self.is_production:
                raise ValueError(
                    "SECRET_KEY is still the insecure default in production. "
                    "Set a strong random SECRET_KEY in the environment before deploying."
                )
            import logging
            logging.getLogger(__name__).warning(
                "SECRET_KEY is the insecure default. This is only safe for local development."
            )
        return self


# Global settings instance
settings = Settings()
