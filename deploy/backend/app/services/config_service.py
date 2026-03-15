"""Runtime configuration service.

Loads API keys/config from system_config DB table at request time.
Falls back to environment variables (settings) if not in DB.
The system_config table is fully managed by Alembic migrations - 
this service does NOT perform any DDL operations.
"""
import logging
from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings

logger = logging.getLogger(__name__)


async def get_runtime_config(db: AsyncSession) -> Dict[str, Any]:
    """Get the full runtime AI/service config from DB with env-var fallbacks."""
    db_cfg: Dict[str, str] = {}
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
        'STRIPE_WEBHOOK_SECRET'  : _get('STRIPE_WEBHOOK_SECRET'),
        'AWS_ACCESS_KEY_ID'     : _get('AWS_ACCESS_KEY_ID'),
        'AWS_SECRET_ACCESS_KEY' : _get('AWS_SECRET_ACCESS_KEY'),
        'AWS_REGION'            : _get('AWS_REGION', 'us-east-1'),
        'AWS_S3_BUCKET'         : _get('AWS_S3_BUCKET'),
        'RESEND_API_KEY'        : _get('RESEND_API_KEY'),
        'RESEND_FROM_EMAIL'     : _get('RESEND_FROM_EMAIL'),
        'SIGNREQUEST_API_KEY'   : _get('SIGNREQUEST_API_KEY'),
        'SIGNWELL_API_KEY'      : _get('SIGNWELL_API_KEY'),
        'SIGNWELL_TEMPLATE_ID'  : _get('SIGNWELL_TEMPLATE_ID'),
    }


async def get_config_value(db: AsyncSession, key: str) -> Optional[str]:
    """Get a single config value from DB, fall back to env/settings."""
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
    from app.models.system_config import SystemConfig

    user_id_str: Optional[str] = str(user_id) if user_id is not None else None
    saved_keys = []

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
            saved_keys.append(key)
        except Exception as exc:
            logger.error(f'[CONFIG] Failed to stage key {key}: {exc}')
            try:
                await db.rollback()
            except Exception:
                pass
            raise RuntimeError(f'Failed to save config key {key}: {exc}') from exc

    try:
        await db.commit()
        logger.info(f'[CONFIG] Committed {len(saved_keys)} config keys to DB')
    except Exception as exc:
        logger.error(f'[CONFIG] Commit failed: {exc}')
        try:
            await db.rollback()
        except Exception:
            pass
        raise RuntimeError(f'Failed to commit config changes: {exc}') from exc
