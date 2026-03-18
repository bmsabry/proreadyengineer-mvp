"""ProReadyEngineer FastAPI application entry point."""

from contextlib import asynccontextmanager

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


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events."""
    # Startup
    print(f"🚀 Starting {settings.PROJECT_NAME} v{settings.VERSION}")
    print(f"📊 Environment: {settings.ENVIRONMENT}")

    yield

    # Shutdown
    print("👋 Shutting down...")
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


    # ---------------------------------------------------------------------------
    # CORS middleware
    # Development always allows localhost. Production allows known origins plus
    # any Render.com preview / deploy URLs.
    # ---------------------------------------------------------------------------
    dev_origins = [
        "http://localhost:3000",
        "http://localhost:8000",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:8000",
    ]

    prod_origins = [
        "https://proreadyengineer.com",
        "https://www.proreadyengineer.com",
        # Render.com deployment URLs - add your actual Render URLs here
        "https://proreadyengineer-frontend.onrender.com",
        "https://proreadyengineer-backend.onrender.com",
    ]

    # Allow additional origins from env var (comma-separated)
    extra_origins_raw = getattr(settings, "EXTRA_CORS_ORIGINS", "") or ""
    extra_origins = [o.strip() for o in extra_origins_raw.split(",") if o.strip()]

    if settings.is_production:
        origins = prod_origins + extra_origins
    else:
        origins = dev_origins + extra_origins

    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_origin_regex=r"https://.*\.onrender\.com",  # all Render preview URLs
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Gzip compression
    app.add_middleware(GZipMiddleware, minimum_size=1000)

    # ===========================================================================
    # API Routers - All routes under /api/v1/ prefix
    # ===========================================================================

    # Auth routes: /api/v1/auth/*
    app.include_router(
        auth_router,
        prefix="/api/v1/auth",
        tags=["Authentication"],
    )

    # Search & Discovery routes: /api/v1/search/*, /api/v1/providers/*
    app.include_router(
        search_router,
        prefix="/api/v1",
        tags=["Search & Discovery"],
    )

    # Provider management routes: /api/v1/provider/*, /api/v1/provider-claims/*
    app.include_router(
        providers_router,
        prefix="/api/v1",
        tags=["Providers"],
    )

    # RFQ routes: /api/v1/rfqs/*, /api/v1/provider/rfqs/*
    app.include_router(
        rfqs_router,
        prefix="/api/v1",
        tags=["RFQs"],
    )

    # Quote routes: /api/v1/customer/*, /api/v1/provider/quotes/*
    app.include_router(
        quotes_router,
        prefix="/api/v1",
        tags=["Quotes"],
    )

    # Payment & Webhook routes: /api/v1/billing/*, /api/v1/webhooks/*
    app.include_router(
        payments_router,
        prefix="/api/v1",
        tags=["Payments & Billing"],
    )

    # Advertising routes: /api/v1/ads/*, /api/v1/advertiser/*
    app.include_router(
        ads_router,
        prefix="/api/v1",
        tags=["Advertising"],
    )

    # Admin routes: /api/v1/admin/*
    app.include_router(
        admin_router,
        prefix="/api/v1",
        tags=["Admin"],
    )

    # ===========================================================================
    # Health & Root Endpoints
    # ===========================================================================

    @app.get("/health", tags=["health"])
    async def health_check():
        """Health check endpoint."""
        return {"status": "healthy", "version": settings.VERSION}

    @app.get("/", tags=["root"])
    async def root():
        """Root endpoint."""
        return {
            "name": settings.PROJECT_NAME,
            "version": settings.VERSION,
            "environment": settings.ENVIRONMENT,
            "docs": "/docs" if not settings.is_production else None,
            "api_version": "v1",
        }

    return app


# Create application instance
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
