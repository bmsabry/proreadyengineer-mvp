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


async def _scheduler_dispatch_job():
    """Called by APScheduler every 5 min poll. Uses fresh sessions to avoid stale-object issues."""
    from app.db.session import AsyncSessionLocal
    from app.models.rfq import RFQ, RfqStatus, RFQDispatchBatch
    from app.services.rfq_service import dispatch_next_batch
    from app.services.config_service import get_runtime_config as _get_runtime_config
    from sqlalchemy import select
    import uuid as _uuid

    logger.info("[scheduler] RFQ batch dispatch poll starting")

    # --- Phase 1: read config and collect open RFQ IDs (one session, read-only) ---
    rfqs_to_check = []  # list of (rfq_id, last_dispatched_at, quote_count)
    interval_hours = float(settings.RFQ_DISPATCH_BATCH_INTERVAL_HOURS)

    async with AsyncSessionLocal() as db:
        try:
            cfg = await _get_runtime_config(db)
            interval_hours = float(cfg.get("RFQ_BATCH_INTERVAL_HOURS",
                                           settings.RFQ_DISPATCH_BATCH_INTERVAL_HOURS))
        except Exception as e:
            logger.warning("[scheduler] config read failed, using default interval: %s", e)

        try:
            result = await db.execute(
                select(RFQ).where(
                    RFQ.is_closed == False,
                    RFQ.rfq_status.in_([
                        RfqStatus.OPEN_FOR_DISPATCH,
                        RfqStatus.OPEN_FOR_UNLOCK,
                        RfqStatus.DISPATCHING,
                    ])
                )
            )
            rfqs = result.scalars().all()
            logger.info("[scheduler] found %d open RFQs", len(rfqs))
        except Exception as e:
            logger.error("[scheduler] failed to query RFQs: %s", e)
            return

        for rfq in rfqs:
            if rfq.quote_count >= 5:
                logger.info("[scheduler] rfq=%s already has %d quotes, skipping", rfq.id, rfq.quote_count)
                continue
            try:
                last_batch_result = await db.execute(
                    select(RFQDispatchBatch)
                    .where(RFQDispatchBatch.rfq_id == rfq.id)
                    .order_by(RFQDispatchBatch.batch_number.desc())
                    .limit(1)
                )
                last_batch = last_batch_result.scalar_one_or_none()
                last_dispatched_at = last_batch.dispatched_at if last_batch else None
                # Snapshot the values we need - don't hold ORM objects across sessions
                rfqs_to_check.append((
                    str(rfq.id),
                    last_dispatched_at,
                    rfq.quote_count,
                ))
            except Exception as e:
                logger.error("[scheduler] error reading rfq=%s batch info: %s", rfq.id, e)

    # --- Phase 2: for each eligible RFQ, open a FRESH session and dispatch ---
    interval_delta = timedelta(hours=interval_hours)
    now = datetime.now(timezone.utc)
    logger.info("[scheduler] interval=%.2fh, checking %d RFQs", interval_hours, len(rfqs_to_check))

    for rfq_id_str, last_dispatched_at, quote_count in rfqs_to_check:
        try:
            should_dispatch = False
            if last_dispatched_at is None:
                should_dispatch = True
                logger.info("[scheduler] rfq=%s no previous batch -> dispatch", rfq_id_str)
            else:
                ld = last_dispatched_at
                if ld.tzinfo is None:
                    ld = ld.replace(tzinfo=timezone.utc)
                elapsed = now - ld
                elapsed_h = elapsed.total_seconds() / 3600
                if elapsed >= interval_delta:
                    should_dispatch = True
                    logger.info("[scheduler] rfq=%s elapsed=%.2fh >= interval=%.2fh -> dispatching",
                                rfq_id_str, elapsed_h, interval_hours)
                else:
                    remaining_min = (interval_delta - elapsed).total_seconds() / 60
                    logger.info("[scheduler] rfq=%s elapsed=%.2fh, %.1f min remaining until next batch",
                                rfq_id_str, elapsed_h, remaining_min)

            if should_dispatch:
                async with AsyncSessionLocal() as fresh_db:
                    rfq_uuid = _uuid.UUID(rfq_id_str)
                    dispatched = await dispatch_next_batch(fresh_db, rfq_uuid)
                    logger.info("[scheduler] rfq=%s dispatched %d providers in new batch",
                                rfq_id_str, len(dispatched))
        except Exception as e:
            logger.error("[scheduler] error dispatching rfq=%s: %s", rfq_id_str, e, exc_info=True)

    logger.info("[scheduler] poll complete")

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events."""
    # Startup
    print(f"Starting {settings.PROJECT_NAME} v{settings.VERSION}")
    print(f"Environment: {settings.ENVIRONMENT}")

    # Start in-process scheduler for RFQ batch dispatch.
    # Polls every 5 minutes. Actual dispatch respects the admin-configured interval.
    # This replaces Celery beat (fork-unsafe) and Render Cron Job (secret/network issues).
    scheduler = None
    try:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        scheduler = AsyncIOScheduler()
        scheduler.add_job(
            _scheduler_dispatch_job,
            "interval",
            minutes=5,
            id="rfq_batch_dispatch",
            replace_existing=True,
            # first run happens after 5 minutes naturally
        )
        scheduler.start()
        logger.info("[scheduler] APScheduler started - RFQ batch dispatch every 5 min poll")
        print("[scheduler] APScheduler started OK")
    except Exception as e:
        logger.error("[scheduler] Failed to start APScheduler: %s", e)
        print(f"[scheduler] WARNING: APScheduler failed to start: {e}")

    yield

    # Shutdown
    if scheduler and scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("[scheduler] APScheduler stopped")
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
            "build_ts": "2026-03-22T21:41:00Z",
            "version": settings.VERSION,
            "note": "APScheduler in-process batch dispatch active."
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
