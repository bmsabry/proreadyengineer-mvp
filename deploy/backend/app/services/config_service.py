"""Runtime configuration service - DEFINITIVE VERSION.

Stores API keys/config in the system_config DB table.
Falls back to environment variables when DB unavailable.

Key design: uses INDEPENDENT database connections for writes
to avoid session corruption from failed SQL operations.
"""
import logging
from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings

logger = logging.getLogger(__name__)


async def _ensure_table_exists(db: AsyncSession) -> bool:
    """Ensure system_config table exists. Returns True if available."""
    try:
        await db.execute(text("SELECT 1 FROM system_config LIMIT 0"))
        return True
    except Exception:
        try:
            await db.rollback()
        except Exception:
            pass
        # Table missing - create it
        try:
            await db.execute(text(
                "CREATE TABLE IF NOT EXISTS system_config ("
                "  id SERIAL PRIMARY KEY,"
                "  key VARCHAR(100) NOT NULL UNIQUE,"
                "  value TEXT,"
                "  is_secret BOOLEAN DEFAULT TRUE,"
                "  created_at TIMESTAMP DEFAULT NOW(),"
                "  updated_at TIMESTAMP DEFAULT NOW(),"
                "  updated_by VARCHAR(255)"
                ")"
            ))
            await db.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_system_config_key ON system_config (key)"
            ))
            await db.commit()
            logger.info("[CONFIG] Created system_config table")
            return True
        except Exception as exc:
            logger.error(f"[CONFIG] Cannot create system_config: {exc}")
            try:
                await db.rollback()
            except Exception:
                pass
            return False


async def _get_table_columns(db: AsyncSession) -> set:
    """Get actual column names of system_config table."""
    try:
        result = await db.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'system_config'"
        ))
        return {row[0] for row in result.fetchall()}
    except Exception as exc:
        logger.warning(f"[CONFIG] Cannot inspect columns: {exc}")
        try:
            await db.rollback()
        except Exception:
            pass
        return set()


async def get_runtime_config(db: AsyncSession) -> Dict[str, Any]:
    """Get full runtime config from DB with env-var fallbacks."""
    from app.db.session import async_engine
    from sqlalchemy.ext.asyncio import AsyncSession as _AsyncSession
    from sqlalchemy.orm import sessionmaker

    db_cfg: Dict[str, str] = {}
    _factory = sessionmaker(async_engine, class_=_AsyncSession, expire_on_commit=False)
    async with _factory() as fresh:
        try:
            result = await fresh.execute(
                text("SELECT key, value FROM system_config WHERE value IS NOT NULL")
            )
            rows = result.fetchall()
            db_cfg = {row[0]: row[1] for row in rows if row[1]}
            logger.debug(f"[CONFIG] Loaded {len(db_cfg)} keys from DB")
        except Exception as exc:
            logger.warning(f"[CONFIG] DB config load failed: {exc}")
            try:
                await fresh.rollback()
            except Exception:
                pass

    def _get(key: str, default: str = '') -> str:
        return (
            db_cfg.get(key)
            or getattr(settings, key.lower(), None)
            or getattr(settings, key, None)
            or default
        )

    return {
        'OPENAI_API_KEY'        : _get('OPENAI_API_KEY'),
        'OPENAI_API_BASE'       : _get('OPENAI_API_BASE', 'https://api.deepinfra.com/v1/openai'),
        'OPENAI_LLM_MODEL'      : _get('OPENAI_LLM_MODEL', 'moonshotai/Kimi-K2.5'),
        'OPENAI_EMBEDDING_MODEL': _get('OPENAI_EMBEDDING_MODEL', 'BAAI/bge-large-en-v1.5'),
        'STRIPE_SECRET_KEY'     : _get('STRIPE_SECRET_KEY'),
        'STRIPE_PUBLISHABLE_KEY': _get('STRIPE_PUBLISHABLE_KEY'),
        'STRIPE_WEBHOOK_SECRET'  : _get('STRIPE_WEBHOOK_SECRET'),
        'AWS_ACCESS_KEY_ID'     : _get('AWS_ACCESS_KEY_ID'),
        'AWS_SECRET_ACCESS_KEY' : _get('AWS_SECRET_ACCESS_KEY'),
        'AWS_REGION'            : _get('AWS_REGION', 'us-east-1'),
        'AWS_S3_BUCKET'         : (db_cfg.get('AWS_S3_BUCKET') or getattr(settings, 'S3_BUCKET_NAME', None) or ''),
        'RESEND_API_KEY'        : _get('RESEND_API_KEY'),
        'RESEND_FROM_EMAIL'     : _get('RESEND_FROM_EMAIL'),
        'SIGNREQUEST_API_KEY'   : _get('SIGNREQUEST_API_KEY'),
        'SIGNWELL_API_KEY'      : _get('SIGNWELL_API_KEY'),
        'SIGNWELL_TEMPLATE_ID'  : _get('SIGNWELL_TEMPLATE_ID'),
        'PAYPAL_CLIENT_ID'             : _get('PAYPAL_CLIENT_ID'),
        'PAYPAL_CLIENT_SECRET'         : _get('PAYPAL_CLIENT_SECRET'),
        'PAYPAL_MODE'                  : _get('PAYPAL_MODE', 'sandbox'),
        'PAYPAL_WEBHOOK_ID'            : _get('PAYPAL_WEBHOOK_ID'),
        'PAYPAL_PLAN_SEARCH_TIER1'     : _get('PAYPAL_PLAN_SEARCH_TIER1'),
        'PAYPAL_PLAN_SEARCH_TIER2'     : _get('PAYPAL_PLAN_SEARCH_TIER2'),
        'PAYPAL_PLAN_PROVIDER_PROFILE' : _get('PAYPAL_PLAN_PROVIDER_PROFILE'),
        'PAYPAL_PLAN_ADVERTISEMENT'    : _get('PAYPAL_PLAN_ADVERTISEMENT'),
        'RFQ_BATCH_SIZE'               : _get('RFQ_BATCH_SIZE', '5'),
        'RFQ_BATCH_INTERVAL_HOURS'     : _get('RFQ_BATCH_INTERVAL_HOURS', '24'),
        'RFQ_CLOSED_MESSAGE'           : _get('RFQ_CLOSED_MESSAGE', 'This RFQ has reached its quote limit. Create a provider account to receive future opportunities.'),
    }


async def get_config_value(db: AsyncSession, key: str) -> Optional[str]:
    """Get a single config value from DB, fall back to env/settings."""
    try:
        result = await db.execute(
            text("SELECT value FROM system_config WHERE key = :key"),
            {"key": key}
        )
        row = result.fetchone()
        if row and row[0]:
            return row[0]
    except Exception as exc:
        logger.debug(f"[CONFIG] DB lookup failed for {key}: {exc}")
        try:
            await db.rollback()
        except Exception:
            pass
    val = getattr(settings, key.lower(), None) or getattr(settings, key, None)
    return str(val) if val else None


async def save_config_values(
    db: AsyncSession,
    config: Dict[str, str],
    user_id: Any = None,
) -> None:
    """Save config key/value pairs to system_config table.

    Uses a FRESH independent connection to avoid session corruption.
    Inspects actual table schema before writing.
    """
    from app.db.session import async_engine
    from sqlalchemy.ext.asyncio import AsyncSession as _AsyncSession
    from sqlalchemy.orm import sessionmaker

    user_id_str = str(user_id) if user_id is not None else None
    now = datetime.utcnow()

    # Use a completely fresh connection - critical for avoiding session corruption
    _factory = sessionmaker(async_engine, class_=_AsyncSession, expire_on_commit=False)

    async with _factory() as fresh:
        try:
            # 1. Ensure table exists
            table_ok = await _ensure_table_exists(fresh)
            if not table_ok:
                raise RuntimeError(
                    "system_config table does not exist and could not be created"
                )

            # 2. Inspect actual columns once
            columns = await _get_table_columns(fresh)
            logger.info(f"[CONFIG] system_config columns: {columns}")

            has_updated_at = 'updated_at' in columns
            has_updated_by = 'updated_by' in columns

            # 3. Build SQL based on actual schema
            if has_updated_by and has_updated_at:
                sql = text(
                    "INSERT INTO system_config (key, value, is_secret, updated_at, updated_by) "
                    "VALUES (:key, :value, TRUE, :now, :uid) "
                    "ON CONFLICT (key) DO UPDATE SET "
                    "value = EXCLUDED.value, updated_at = EXCLUDED.updated_at, "
                    "updated_by = EXCLUDED.updated_by"
                )
            elif has_updated_at:
                sql = text(
                    "INSERT INTO system_config (key, value, is_secret, updated_at) "
                    "VALUES (:key, :value, TRUE, :now) "
                    "ON CONFLICT (key) DO UPDATE SET "
                    "value = EXCLUDED.value, updated_at = EXCLUDED.updated_at"
                )
            else:
                sql = text(
                    "INSERT INTO system_config (key, value, is_secret) "
                    "VALUES (:key, :value, TRUE) "
                    "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value"
                )

            # 4. Execute all upserts
            saved = []
            for key, value in config.items():
                if value is None:
                    continue
                params: Dict[str, Any] = {"key": key, "value": value}
                if has_updated_at:
                    params["now"] = now
                if has_updated_by:
                    params["uid"] = user_id_str
                await fresh.execute(sql, params)
                saved.append(key)
                logger.info(f"[CONFIG] Upserted: {key}")

            # 5. Commit
            await fresh.commit()
            logger.info(f"[CONFIG] Committed {len(saved)} keys: {saved}")

        except Exception as exc:
            logger.error(f"[CONFIG] Save failed: {exc}", exc_info=True)
            try:
                await fresh.rollback()
            except Exception:
                pass
            raise RuntimeError(f"Config save failed: {exc}") from exc
