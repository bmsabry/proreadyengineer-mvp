"""ProReadyEngineer FastAPI application entry point."""

from contextlib import asynccontextmanager
from datetime import datetime, timezone, timedelta
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

import os
import sentry_sdk
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.core.config import settings
from app.db.session import close_db
from app.api.endpoints import (
    auth_router,
    search_router,
    providers_router,
    rfqs_router,
    quotes_router,
    payments_router,
    ads_router,
    admin_router,
)
from app.api.endpoints.internal import router as internal_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events."""
    print(f"Starting {settings.PROJECT_NAME} v{settings.VERSION}")
    print(f"Environment: {settings.ENVIRONMENT}")

    # -----------------------------------------------------------------------
    # RFQ BATCH DISPATCH is handled EXCLUSIVELY by the Render Cron Job
    # (proreadyengineer-rfq-cron) which POSTs to:
    #   /api/v1/internal/cron/dispatch-rfq-batches  every 15 minutes
    #
    # DO NOT re-enable APScheduler or any in-process scheduler here.
    # Running two concurrent dispatch triggers (APScheduler + Render Cron)
    # creates race conditions that cause:
    #   - Emails sent to providers of CANCELLED RFQs
    #   - Emails sent to providers not yet due for contact
    #   - Duplicate batch emails to same providers
    # Single dispatch trigger = Render Cron Job only.
    # -----------------------------------------------------------------------
    logger.info("[startup] Render Cron Job is sole RFQ dispatch trigger. APScheduler intentionally disabled.")
    print("[startup] APScheduler disabled. Render Cron Job handles RFQ batch dispatch.")

    yield

    print("Shutting down...")
    await close_db()


def create_application() -> FastAPI:
    """Application factory."""
    app = FastAPI(
        title=settings.PROJECT_NAME,
        version=settings.VERSION,
        description="B2B Engineering Services Directory and Marketplace",
        docs_url="/docs" if not settings.is_production else None,
        redoc_url="/redoc" if not settings.is_production else None,
        openapi_url="/openapi.json" if not settings.is_production else None,
        lifespan=lifespan,
    )

    # Rate limiting
    limiter = Limiter(key_func=get_remote_address, default_limits=["200/minute"])
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(SlowAPIMiddleware)

    dev_origins = [
        "http://localhost:3000",
        "http://localhost:8000",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:8000",
    ]

    prod_origins = [
        "https://proreadyengineer.com",
        "https://www.proreadyengineer.com",
        "https://proreadyengineer-frontend.onrender.com",
        "https://proreadyengineer-backend.onrender.com",
    ]

    extra_origins_raw = getattr(settings, "EXTRA_CORS_ORIGINS", "") or ""
    extra_origins = [o.strip() for o in extra_origins_raw.split(",") if o.strip()]

    if settings.is_production:
        origins = prod_origins + extra_origins
    else:
        origins = dev_origins + extra_origins

    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_origin_regex=r"https://.*\.onrender\.com",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.add_middleware(GZipMiddleware, minimum_size=1000)

    app.include_router(auth_router, prefix="/api/v1/auth", tags=["Authentication"])
    app.include_router(search_router, prefix="/api/v1", tags=["Search & Discovery"])
    app.include_router(providers_router, prefix="/api/v1", tags=["Providers"])
    app.include_router(rfqs_router, prefix="/api/v1", tags=["RFQs"])
    app.include_router(quotes_router, prefix="/api/v1", tags=["Quotes"])
    app.include_router(payments_router, prefix="/api/v1", tags=["Payments & Billing"])
    app.include_router(ads_router, prefix="/api/v1", tags=["Advertising"])
    app.include_router(admin_router, prefix="/api/v1", tags=["Admin"])
    app.include_router(internal_router, prefix="/api/v1", tags=["internal"])

    @app.get("/health", tags=["health"])
    async def health_check():
        return {"status": "healthy", "version": settings.VERSION}

    @app.get("/", tags=["root"])
    async def root():
        return {
            "name": settings.PROJECT_NAME,
            "version": settings.VERSION,
            "environment": settings.ENVIRONMENT,
            "docs": "/docs" if not settings.is_production else None,
            "api_version": "v1",
        }

    @app.get("/api/v1/build-info")
    async def build_info():
        return {
            "build_ts": "2026-03-28T09:30:00Z",
            "version": settings.VERSION,
            "note": "Render Cron Job handles RFQ dispatch. APScheduler disabled to prevent rogue emails."
        }

    return app


app = create_application()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG,
        log_level="info",
    )
