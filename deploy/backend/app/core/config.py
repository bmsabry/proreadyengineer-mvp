"""Pydantic settings configuration for the application."""

from typing import List, Optional, Union
from pydantic import field_validator
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
    FROM_EMAIL: str = os.getenv("FROM_EMAIL", "info@ProMechDirectory.com")
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
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
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
    SIGNREQUEST_API_KEY: Optional[str] = None
    SIGNREQUEST_SUBDOMAIN: Optional[str] = None
    SIGNREQUEST_WEBHOOK_SECRET: Optional[str] = None

    # Email
    EMAIL_PROVIDER: str = "resend"
    RESEND_API_KEY: Optional[str] = None
    SENDGRID_API_KEY: Optional[str] = None
    EMAIL_FROM: str = "info@ProMechDirectory.com"
    EMAIL_FROM_NAME: str = "ProMechDirectory"

    # OpenAI
    OPENAI_API_KEY: Optional[str] = None
    OPENAI_API_BASE: Optional[str] = None
    OPENAI_EMBEDDING_MODEL: str = "BAAI/bge-large-en-v1.5"
    OPENAI_LLM_MODEL: str = "gpt-4o-mini"

    # Search & Quotas (in cents)
    ANONYMOUS_SEARCH_LIMIT_PER_MONTH: int = 3
    REGISTERED_SEARCH_LIMIT_PER_MONTH: int = 10
    SEARCH_TIER_1_LIMIT: int = 100
    SEARCH_TIER_1_PRICE: int = 1000  # $10.00
    SEARCH_TIER_2_LIMIT: int = 200
    SEARCH_TIER_2_PRICE: int = 2000  # $20.00
    RFQ_UNLOCK_PRICE: int = 1000  # $10.00
    NDA_FEE_PRICE: int = 500  # $5.00
    PROVIDER_SUBSCRIPTION_PRICE: int = 1000  # $10.00
    AD_SUBSCRIPTION_PRICE: int = 5000  # $50.00

    # RFQ Settings
    RFQ_MAX_QUOTES: int = 5
    RFQ_DISPATCH_BATCH_SIZE: int = 5
    RFQ_DISPATCH_BATCH_INTERVAL_HOURS: int = 24

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


# Global settings instance
settings = Settings()
