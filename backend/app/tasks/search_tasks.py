"""Search background tasks."""

import asyncio
import logging
from datetime import datetime

from app.core.celery import celery_app
from app.db.session import AsyncSessionLocal
from app.services.search_service import generate_embedding

_log = logging.getLogger(__name__)


async def generate_provider_embedding_async(provider_id: str) -> None:
    """Generate embedding in-process (no Celery worker required)."""
    try:
        from sqlalchemy import select
        from app.models.provider import Provider
        from app.services.search_service import _provider_embed_text
        from app.services.config_service import get_runtime_config

        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(Provider).where(Provider.id == int(provider_id))
            )
            provider = result.scalar_one_or_none()
            if provider:
                embed_text = _provider_embed_text(provider)
                if embed_text.strip():
                    # Bounded retry: a transient embedding-API blip self-heals here
                    # instead of leaving the vector stale until the next profile edit.
                    # Config errors (no API key) raise immediately — retrying won't help.
                    embedding = None
                    for attempt in range(3):
                        try:
                            embedding = await generate_embedding(embed_text)
                            break
                        except ValueError:
                            raise
                        except Exception as exc:
                            if attempt >= 2:
                                raise
                            _log.warning(
                                "Embedding attempt %d/3 failed for provider %s: %s; retrying",
                                attempt + 1, provider_id, exc,
                            )
                            await asyncio.sleep(1.0 * (attempt + 1))
                    provider.embedding = embedding
                    cfg = await get_runtime_config(db)
                    provider.embedding_model = (
                        cfg.get('OPENAI_EMBEDDING_MODEL') or 'text-embedding-3-small'
                    )
                    provider.embedding_generated_at = datetime.utcnow()
                    await db.commit()
                    _log.info("Embedding updated for provider %s", provider_id)
    except Exception as exc:
        _log.warning("Background embedding failed for provider %s: %s", provider_id, exc)


async def reembed_missing_provider_embeddings(limit: int = 25) -> dict:
    """Backstop: re-embed providers whose embedding never generated (NULL).

    In-process and bounded; safe to call repeatedly. Catches the rare case where
    a profile save's inline re-embed failed (e.g. a prolonged embedding-API
    outage), so those providers don't stay invisible to search until their next
    edit. Returns {scanned, succeeded, failed}.
    """
    from sqlalchemy import select, func
    from app.models.provider import Provider
    async with AsyncSessionLocal() as db:
        ids = (await db.execute(
            select(Provider.id).where(Provider.embedding.is_(None)).limit(limit)
        )).scalars().all()
    for pid in ids:
        await generate_provider_embedding_async(str(pid))  # internally retried + non-fatal
    still_null = 0
    if ids:
        async with AsyncSessionLocal() as db:
            still_null = int((await db.execute(
                select(func.count()).select_from(Provider).where(
                    Provider.id.in_(ids), Provider.embedding.is_(None)
                )
            )).scalar() or 0)
    return {"scanned": len(ids), "succeeded": len(ids) - still_null, "failed": still_null}


@celery_app.task(bind=True, max_retries=3)
def generate_provider_embedding_task(self, provider_id: str):
    """Generate embedding for provider using full enriched text."""
    async def _generate():
        await generate_provider_embedding_async(provider_id)

    try:
        asyncio.run(_generate())
    except Exception as exc:
        raise self.retry(exc=exc)


@celery_app.task(bind=True)
def reindex_all_providers_task(self):
    """Regenerate embeddings for all providers (admin maintenance)."""
    async def _reindex():
        from sqlalchemy import select
        from app.models.provider import Provider

        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Provider))
            providers = result.scalars().all()

            for provider in providers:
                await generate_provider_embedding_async(str(provider.id))

    asyncio.run(_reindex())
