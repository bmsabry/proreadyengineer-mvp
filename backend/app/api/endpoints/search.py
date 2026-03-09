"""Search API endpoints with comprehensive debugging."""

import logging
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import Optional

from app.api.deps import get_db, get_current_user_optional, get_client_ip
from app.schemas.search import SearchRequest, SearchResponse, SearchResult
from app.schemas.provider import ProviderPublicResponse
from app.services.search_service import search_providers, check_search_quota
from app.services.file_service import generate_upload_url
from app.models.user import User
from app.models.provider import Provider
from app.core.config import settings

router = APIRouter()
logger = logging.getLogger(__name__)

# In-memory store for last search error (for debugging)
_last_search_error = {"error": None, "timestamp": None, "query": None}


@router.post("/query", response_model=SearchResponse)
async def search_query(
    request: Request,
    data: SearchRequest,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """Search providers with natural language query."""
    global _last_search_error

    user_id = current_user.id if current_user else None
    ip = get_client_ip(request)

    logger.info(f"[SEARCH] Query received: user_id={user_id}, ip={ip}, query='{data.query[:100]}...'")
    logger.info(f"[SEARCH] Filters: {data.filters}")

    # Check quota
    try:
        can_search, remaining = await check_search_quota(db, current_user, ip)
        logger.info(f"[SEARCH] Quota check: can_search={can_search}, remaining={remaining}")
    except Exception as e:
        logger.error(f"[SEARCH] Quota check failed: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to check search quota"
        )

    if not can_search:
        logger.warning(f"[SEARCH] Quota exceeded for user_id={user_id}, ip={ip}")
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Search quota exceeded. Please upgrade your plan."
        )

    # Perform search
    try:
        results = await search_providers(
            db,
            query=data.query,
            filters=data.filters or {},
            limit=50
        )

        result_count = len(results)
        logger.info(f"[SEARCH] Search completed: {result_count} results found")

        # Clear last error on success
        _last_search_error = {"error": None, "timestamp": None, "query": data.query}

        return SearchResponse(
            results=[SearchResult(
                provider=ProviderPublicResponse.from_orm(r.provider),
                score=r.score,
                explanation=r.explanation
            ) for r in results[:5]],
            total_matches=len(results),
            search_quota_remaining=remaining - 1 if remaining > 0 else 0
        )

    except HTTPException:
        raise
    except Exception as e:
        error_msg = str(e)
        logger.error(f"[SEARCH] Search failed: {error_msg}", exc_info=True)
        _last_search_error = {
            "error": error_msg,
            "timestamp": datetime.utcnow().isoformat(),
            "query": data.query
        }
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Search failed: {error_msg}"
        )


@router.get("/debug")
async def search_debug(
    db: AsyncSession = Depends(get_db),
):
    """Debug endpoint to check search system status."""
    logger.info("[SEARCH DEBUG] Debug endpoint called")

    debug_info = {
        "timestamp": datetime.utcnow().isoformat(),
        "database": {},
        "api_keys": {},
        "last_error": _last_search_error
    }

    # Check provider count
    try:
        result = await db.execute(select(func.count()).select_from(Provider))
        provider_count = result.scalar()
        debug_info["database"]["provider_count"] = provider_count

        # Check providers with embeddings
        result = await db.execute(
            select(func.count()).select_from(Provider).where(Provider.embedding.isnot(None))
        )
        embedded_count = result.scalar()
        debug_info["database"]["providers_with_embeddings"] = embedded_count

        # Sample a provider
        result = await db.execute(select(Provider).limit(1))
        sample = result.scalar_one_or_none()
        if sample:
            debug_info["database"]["sample_provider"] = {
                "id": str(sample.id),
                "name": sample.name,
                "has_embedding": sample.embedding is not None
            }

        debug_info["database"]["connection_ok"] = True
    except Exception as e:
        logger.error(f"[SEARCH DEBUG] Database check failed: {str(e)}")
        debug_info["database"]["connection_ok"] = False
        debug_info["database"]["error"] = str(e)

    # Check API keys
    debug_info["api_keys"]["openai_configured"] = bool(settings.OPENAI_API_KEY and settings.OPENAI_API_KEY != "dummy-key")
    debug_info["api_keys"]["openai_base_url"] = settings.OPENAI_API_BASE or "default (OpenAI)"
    debug_info["api_keys"]["embedding_model"] = settings.OPENAI_EMBEDDING_MODEL
    debug_info["api_keys"]["llm_model"] = settings.OPENAI_LLM_MODEL

    return debug_info


@router.post("/upload/initiate")
async def upload_initiate(
    filename: str,
    content_type: str,
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """Get presigned URL for document upload."""
    logger.info(f"[SEARCH UPLOAD] Initiating upload: filename={filename}, content_type={content_type}")
    import uuid
    key = f"search-uploads/{current_user.id if current_user else 'anon'}/{uuid.uuid4()}/{filename}"
    url_data = generate_upload_url(key, content_type)
    return {"upload_url": url_data["url"], "fields": url_data["fields"], "key": key}


@router.post("/upload/complete")
async def upload_complete(
    key: str,
    db: AsyncSession = Depends(get_db),
):
    """Process uploaded document for search."""
    logger.info(f"[SEARCH UPLOAD] Processing uploaded document: key={key}")
    from app.services.file_service import extract_document_text
    try:
        text = await extract_document_text(key)
        logger.info(f"[SEARCH UPLOAD] Extracted {len(text)} characters from document")
        return {"extracted_text": text[:5000], "key": key}
    except Exception as e:
        logger.error(f"[SEARCH UPLOAD] Failed to extract document: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process document: {str(e)}"
        )


@router.get("/providers/{provider_id}/public", response_model=ProviderPublicResponse)
async def get_provider_public(
    provider_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get public provider profile."""
    from sqlalchemy import select
    from app.models.provider import Provider

    result = await db.execute(select(Provider).where(Provider.id == provider_id))
    provider = result.scalar_one_or_none()

    if not provider:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Provider not found")

    return ProviderPublicResponse.from_orm(provider)
