"""Runtime configuration service.

Loads API keys/config from system_config DB table at request time.
Falls back to environment variables (settings) if not in DB.
This allows admin UI to save keys to DB and have them take effect immediately
without restarting the server.
"""
import logging
from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings

logger = logging.getLogger(__name__)


async def _ensure_table(db: AsyncSession) -> None:
    """Create system_config table if it does not exist, and add/fix missing columns."""
    try:
        await db.execute(text("""
            CREATE TABLE IF NOT EXISTS system_config (
                id SERIAL PRIMARY KEY,
                key VARCHAR(100) UNIQUE NOT NULL,
                value TEXT,
                is_secret BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW(),
                updated_by VARCHAR(100)
            )
        """))
        await db.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_system_config_key ON system_config (key)"
        ))
        # Add created_at if missing (tables created without it)
        await db.execute(text("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name='system_config' AND column_name='created_at'
                ) THEN
                    ALTER TABLE system_config ADD COLUMN created_at TIMESTAMP DEFAULT NOW();
                END IF;
            END$$;
        """))
        # CRITICAL FIX: migrate updated_by from INTEGER to VARCHAR if needed
        # Handles existing production tables created with INTEGER type
        await db.execute(text("""
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name='system_config'
                      AND column_name='updated_by'
                      AND data_type IN ('integer', 'bigint', 'smallint')
                ) THEN
                    ALTER TABLE system_config
                        ALTER COLUMN updated_by TYPE VARCHAR(100)
                        USING COALESCE(updated_by::TEXT, NULL);
                END IF;
            END$$;
        """))
        await db.commit()
    except Exception as exc:
        logger.warning(f'[CONFIG] Could not ensure system_config table: {exc}')
        try:
            await db.rollback()
        except Exception:
            pass


async def get_runtime_config(db: AsyncSession) -> Dict[str, Any]:
    """Get the full runtime AI/service config from DB with env-var fallbacks."""
    await _ensure_table(db)
    try:
        from app.models.system_config import SystemConfig
        result = await db.execute(select(SystemConfig))
        records = result.scalars().all()
        db_cfg = {r.key: r.value for r in records if r.value}
        logger.debug(f'[CONFIG] Loaded {len(db_cfg)} keys from DB')
    except Exception as exc:
        logger.warning(f'[CONFIG] DB config load failed: {exc}')
        try:
            await db.rollback()
        except Exception:
            pass
        db_cfg = {}

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
        'OPENAI_LLM_MODEL'      : _get('OPENAI_LLM_MODEL', 'moonshotai/kimi-k2.5'),
        'OPENAI_EMBEDDING_MODEL': _get('OPENAI_EMBEDDING_MODEL', 'BAAI/bge-large-en-v1.5'),
        'STRIPE_SECRET_KEY'     : _get('STRIPE_SECRET_KEY'),
        'STRIPE_PUBLISHABLE_KEY': _get('STRIPE_PUBLISHABLE_KEY'),
        'STRIPE_WEBHOOK_SECRET' : _get('STRIPE_WEBHOOK_SECRET'),
        'AWS_ACCESS_KEY_ID'     : _get('AWS_ACCESS_KEY_ID'),
        'AWS_SECRET_ACCESS_KEY' : _get('AWS_SECRET_ACCESS_KEY'),
        'AWS_REGION'            : _get('AWS_REGION', 'us-east-1'),
        'AWS_S3_BUCKET'         : _get('AWS_S3_BUCKET'),
        'RESEND_API_KEY'        : _get('RESEND_API_KEY'),
        'RESEND_FROM_EMAIL'     : _get('RESEND_FROM_EMAIL'),
        'SIGNREQUEST_API_KEY'   : _get('SIGNREQUEST_API_KEY'),
        'SIGNWELL_API_KEY'      : _get('SIGNWELL_API_KEY'),
        'SIGNWELL_TEMPLATE_ID'  : _get('SIGNWELL_TEMPLATE_ID'),
        'SIGNWELL_WEBHOOK_SECRET': _get('SIGNWELL_WEBHOOK_SECRET'),
    }


async def get_config_value(db: AsyncSession, key: str) -> Optional[str]:
    """Get a single config value from DB, fall back to env/settings."""
    await _ensure_table(db)
    try:
        from app.models.system_config import SystemConfig
        result = await db.execute(
            select(SystemConfig).where(SystemConfig.key == key)
        )
        record = result.scalar_one_or_none()
        if record and record.value:
            return record.value
    except Exception as exc:
        logger.debug(f'[CONFIG] DB lookup failed for {key}: {exc}')
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
    """Upsert config key/value pairs into the system_config table."""
    await _ensure_table(db)
    from app.models.system_config import SystemConfig

    # Always convert user_id to string — handles UUID, int, str, or None safely
    user_id_str: Optional[str] = str(user_id) if user_id is not None else None

    errors = []
    for key, value in config.items():
        if value is None:
            continue
        try:
            result = await db.execute(
                select(SystemConfig).where(SystemConfig.key == key)
            )
            record = result.scalar_one_or_none()
            if record:
                record.value = value
                record.updated_at = datetime.utcnow()
                record.updated_by = user_id_str
                logger.info(f'[CONFIG] Updated key: {key}')
            else:
                db.add(SystemConfig(
                    key=key,
                    value=value,
                    is_secret=True,
                    updated_at=datetime.utcnow(),
                    updated_by=user_id_str,
                ))
                logger.info(f'[CONFIG] Inserted key: {key}')
        except Exception as exc:
            logger.error(f'[CONFIG] Failed to stage key {key}: {exc}')
            errors.append(f'{key}: {exc}')

    if errors:
        raise RuntimeError("Failed to save config keys: " + ", ".join(errors))

    await db.commit()
    logger.info(f'[CONFIG] Committed {len(config)} config keys to DB')
