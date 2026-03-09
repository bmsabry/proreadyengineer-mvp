"""Search background tasks."""

import asyncio
from datetime import datetime

from app.core.celery import celery_app
from app.db.session import AsyncSessionLocal
from app.services.search_service import generate_embedding


@celery_app.task(bind=True, max_retries=3)
def generate_provider_embedding_task(self, provider_id: str):
    """Generate embedding for provider description."""
    async def _generate():
        from sqlalchemy import select
        from app.models.provider import Provider

        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(Provider).where(Provider.id == provider_id)
            )
            provider = result.scalar_one_or_none()

            if provider and provider.business_description:
                embedding = await generate_embedding(provider.business_description)
                provider.embedding = embedding
                provider.embedding_model = "text-embedding-3-small"
                provider.embedding_generated_at = datetime.utcnow()
                await db.commit()

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
                if provider.business_description:
                    generate_provider_embedding_task.delay(str(provider.id))

    asyncio.run(_reindex())
