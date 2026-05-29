"""ProReadyEngineer FastAPI application entry point."""

from contextlib import asynccontextmanager
from datetime import datetime, timezone, timedelta
import logging
import asyncio
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse

import os
import sentry_sdk
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.core.rate_limiter import limiter
from app.core.config import settings
from app.db.session import close_db
from app.api.endpoints import (
    support_router,
    auth_router,
    search_router,
    providers_router,
    rfqs_router,
    quotes_router,
    payments_router,
    ads_router,
    admin_router,
    campaigns_router,
    help_router,
)
from app.api.endpoints.internal import router as internal_router

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Sentry initialisation (gated on SENTRY_DSN env var - does nothing if not set)
# ---------------------------------------------------------------------------
_SENTRY_DSN = os.getenv('SENTRY_DSN', '')
if _SENTRY_DSN:
    sentry_sdk.init(
        dsn=_SENTRY_DSN,
        traces_sample_rate=0.1,
        environment=os.getenv('ENVIRONMENT', 'development'),
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events."""
    print(f"Starting {settings.PROJECT_NAME} v{settings.VERSION}")
    print(f"Environment: {settings.ENVIRONMENT}")

    # -----------------------------------------------------------------------
    # RFQ BATCH DISPATCH - DUAL TRIGGER ARCHITECTURE
    #
    # PRIMARY:  Render Cron Job (proreadyengineer-rfq-cron in render.yaml)
    #           Fires every 15 min via POST /api/v1/internal/cron/dispatch-rfq-batches
    #           REQUIRES: Blueprint sync on Render dashboard to activate.
    #
    # BACKUP:   asyncio background task (below) - fires every 15 min inside
    #           the FastAPI process. Ensures dispatch works even when the
    #           Render Cron service is not yet synced or temporarily down.
    #
    # SAFE:     Dual interval guard in internal.py AND dispatch_next_batch
    #           prevents duplicate batches even when both triggers fire.
    # -----------------------------------------------------------------------

    async def _dispatch_loop():
        """Asyncio background dispatch loop - backup trigger every 5 minutes.

        Why 5 min not 15: with a 30-min RFQ_BATCH_INTERVAL_HOURS, a 15-min
        poll routinely misses the dispatch window when ticks fall right
        before the interval elapses (e.g. last batch 12:36 -> 13:06 tick
        sees elapsed=29min<30 -> skip -> next tick 13:21 = 45min later,
        looks broken to user). 5-min poll closes that gap; the interval
        guard in internal.py + rfq_service.py prevents over-dispatch.
        """
        from app.db.session import AsyncSessionLocal
        logger.info("[dispatch_loop] Background dispatch loop started (5-min interval)")
        await asyncio.sleep(5)   # wait 5s on startup to let DB connections initialize
        while True:
            try:
                from app.api.endpoints.internal import cron_dispatch_rfq_batches
                async with AsyncSessionLocal() as db:
                    # trigger_source="asyncio_loop" lets the admin Cron Health card
                    # detect the case where the Render cron is dead and only the
                    # backup loop is carrying.
                    result = await cron_dispatch_rfq_batches(db=db, trigger_source="asyncio_loop")
                    logger.info(
                        "[dispatch_loop] fired: open=%s dispatched=%s skipped=%s interval=%.2fh",
                        result.get("open_rfqs_found", 0),
                        len(result.get("dispatched", [])),
                        len(result.get("skipped", [])),
                        result.get("interval_hours", 0),
                    )
            except Exception as exc:
                logger.error("[dispatch_loop] error: %s", exc, exc_info=True)
            await asyncio.sleep(300)  # 300 seconds = 5 minutes

    dispatch_task = asyncio.create_task(_dispatch_loop())
    logger.info("[startup] asyncio dispatch backup loop started (5-min interval)")
    logger.info("[startup] Render Cron Job is PRIMARY dispatch trigger. asyncio loop is BACKUP.")
    print("[startup] Dual dispatch triggers: Render Cron (primary) + asyncio loop (backup).")

    yield

    dispatch_task.cancel()
    try:
        await dispatch_task
    except asyncio.CancelledError:
        pass
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

    # -----------------------------------------------------------------------
    # Rate limiting (uses module-level limiter from app.core.rate_limiter)
    # -----------------------------------------------------------------------
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(SlowAPIMiddleware)

    # -----------------------------------------------------------------------
    # CORS - origins from ALLOWED_ORIGINS env var (comma-separated)
    # Default: localhost:3000,localhost:3001 for development
    # Production: set ALLOWED_ORIGINS=https://promechdirectory.com,https://www.promechdirectory.com
    # -----------------------------------------------------------------------
    # Collect origins from both ALLOWED_ORIGINS and EXTRA_CORS_ORIGINS env vars
    allowed_origins_raw = getattr(settings, 'ALLOWED_ORIGINS', 'http://localhost:3000,http://localhost:3001')
    extra_origins_raw = getattr(settings, 'EXTRA_CORS_ORIGINS', '')
    combined = f"{allowed_origins_raw},{extra_origins_raw}"
    allowed_origins = [o.strip() for o in combined.split(',') if o.strip()]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        # Scoped to THIS project's own Render services (not any *.onrender.com site).
        allow_origin_regex=r"https://(proreadyengineer|promechdirectory)[a-z0-9-]*\.onrender\.com",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.add_middleware(GZipMiddleware, minimum_size=1000)

    # -----------------------------------------------------------------------
    # Security headers middleware
    # -----------------------------------------------------------------------
    @app.middleware("http")
    async def add_security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: https:; "
            "connect-src 'self' https://api.stripe.com https://js.stripe.com; "
            "frame-src https://js.stripe.com https://hooks.stripe.com"
        )
        return response

    # -----------------------------------------------------------------------
    # Generic exception handler - never expose stack traces in responses
    # -----------------------------------------------------------------------
    from fastapi import HTTPException

    @app.exception_handler(Exception)
    async def generic_exception_handler(request: Request, exc: Exception):
        if isinstance(exc, HTTPException):
            raise exc
        logger.exception("Unhandled exception on %s %s", request.method, request.url)
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error"},
        )

    app.include_router(auth_router, prefix="/api/v1/auth", tags=["Authentication"])
    app.include_router(search_router, prefix="/api/v1", tags=["Search & Discovery"])
    app.include_router(providers_router, prefix="/api/v1", tags=["Providers"])
    app.include_router(rfqs_router, prefix="/api/v1", tags=["RFQs"])
    app.include_router(quotes_router, prefix="/api/v1", tags=["Quotes"])
    app.include_router(payments_router, prefix="/api/v1", tags=["Payments & Billing"])
    app.include_router(ads_router, prefix="/api/v1", tags=["Advertising"])
    app.include_router(admin_router, prefix="/api/v1", tags=["Admin"])
    app.include_router(campaigns_router, prefix="/api/v1", tags=["Campaigns"])
    app.include_router(support_router, prefix="/api/v1", tags=["Support"])
    app.include_router(help_router, prefix="/api/v1", tags=["Help"])
    app.include_router(internal_router, prefix="/api/v1", tags=["internal"])
    # ALSO register internal router at root prefix so BOTH URLs work:
    # /internal/cron/dispatch-rfq-batches (Render cron job historical URL)
    # /api/v1/internal/cron/dispatch-rfq-batches (canonical URL)
    app.include_router(internal_router, prefix="", tags=["internal-root"])

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
