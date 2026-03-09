"""ProReadyEngineer FastAPI application entry point."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

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

    # CORS middleware
    origins = [
        "http://localhost:3000",  # Next.js dev server
        "http://localhost:8000",
        "https://proreadyengineer-web.onrender.com",  # Render deployment
        "https://proreadyengineer.com",
        "https://www.proreadyengineer.com",
    ]
    # Also allow any preview deployments
    if settings.FRONTEND_URL and settings.FRONTEND_URL not in origins:
        origins.append(settings.FRONTEND_URL)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Gzip compression
    app.add_middleware(GZipMiddleware, minimum_size=1000)

    # =============================================================================
    # API Routers - All routes under /api/v1/ prefix
    # =============================================================================

    # Auth: 8 routes
    # - POST /auth/register, /auth/login, /auth/refresh
    # - POST /auth/logout, /auth/logout-all
    # - POST /auth/password/forgot, /auth/password/reset
    # - GET /auth/me
    app.include_router(
        auth_router,
        prefix="/api/v1/auth",
        tags=["Authentication"],
    )

    # Search & Discovery: 5 routes
    # - POST /search/query, /search/upload/initiate, /search/upload/complete
    # - GET /providers/{id}/public
    # - POST /providers/claim-search
    app.include_router(
        search_router,
        prefix="/api/v1/search",
        tags=["Search & Discovery"],
    )

    # Providers: 10 routes
    # - POST /provider-claims, GET /provider-claims/me
    # - GET /admin/provider-claims, POST /admin/provider-claims/{id}/approve|reject
    # - GET /provider/profile, POST /provider/profile, PATCH /provider/profile
    # - POST /provider/profile/request-rank-up, GET /provider/memberships
    app.include_router(
        providers_router,
        prefix="/api/v1",
    )

    # RFQs: 13 routes
    # Customer: POST /rfqs, GET /rfqs/{id}, POST /rfqs/{id}/files/initiate|complete
    #           POST /rfqs/{id}/nda/checkout, GET /rfqs/{id}/status, POST /rfqs/{id}/submit
    # Provider: GET /provider/rfqs/teasers, GET /provider/rfqs/{id}/teaser
    #           POST /provider/rfqs/{id}/unlock/checkout, GET /provider/rfqs/{id}/unlock/status
    #           GET /provider/rfqs/{id}/files, POST /provider/rfqs/{id}/quote
    app.include_router(
        rfqs_router,
        prefix="/api/v1",
    )

    # Quotes: 4 routes
    # - GET /customer/rfqs/{id}/quotes, POST /customer/quotes/{id}/accept
    # - POST /provider/quotes/{id}/withdraw, GET /provider/quotes/me
    app.include_router(
        quotes_router,
        prefix="/api/v1",
    )

    # Payments & Billing: 4 routes
    # - GET /billing/portal
    # - POST /webhooks/stripe, /webhooks/paypal, /webhooks/signrequest
    app.include_router(
        payments_router,
        prefix="/api/v1",
    )

    # Advertising: 7 routes
    # - GET /ads/software-providers, GET /ads/featured-firms
    # - POST /ads/checkout, GET /advertiser/ads/me
    # - POST /advertiser/ads/{id}/asset/initiate|complete, PATCH /advertiser/ads/{id}
    app.include_router(
        ads_router,
        prefix="/api/v1",
    )

    # Admin: 12 routes
    # - GET /admin/rfqs, GET /admin/rfqs/{id}, POST /admin/rfqs/{id}/override-status
    # - GET /admin/payments, GET /admin/webhooks, POST /admin/webhooks/{id}/replay
    # - GET /admin/tier-requests, POST /admin/tier-requests/{id}/approve|reject
    # - GET /admin/ads, POST /admin/ads/{id}/pause, POST /admin/users/{id}/suspend
    app.include_router(
        admin_router,
        prefix="/api/v1",
    )

    # =============================================================================
    # Health & Root Endpoints
    # =============================================================================

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
            "total_endpoints": 63,
        }

    return app


# Create application instance
app = create_application()




@app.get("/debug/simple-test")
async def debug_simple_test():
    """Simplest possible test endpoint."""
    return {"status": "ok", "message": "Basic endpoint works"}


@app.post("/debug/search-test")
async def debug_search_test(query: str = "test"):
    """Test search without database dependency."""
    return {"status": "ok", "query": query, "mode": "no-db"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG,
        log_level="info",
    )
