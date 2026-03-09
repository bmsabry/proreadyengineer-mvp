"""Search API endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from app.api.deps import get_db, get_current_user_optional, get_client_ip
from app.schemas.search import SearchRequest, SearchResponse, SearchResult
from app.schemas.provider import ProviderPublicResponse
from app.services.search_service import search_providers, check_search_quota
from app.services.file_service import generate_upload_url
from app.models.user import User

router = APIRouter()


@router.post("/query", response_model=SearchResponse)
async def search_query(
    request: Request,
    data: SearchRequest,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """Search providers with natural language query."""
    # Check quota
    ip = get_client_ip(request)
    can_search, remaining = await check_search_quota(db, current_user, ip)

    if not can_search:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Search quota exceeded. Please upgrade your plan."
        )

    # Perform search
    results = await search_providers(
        db, 
        query=data.query,
        filters=data.filters or {},
        limit=50
    )

    return SearchResponse(
        results=[SearchResult(
            provider=ProviderPublicResponse.from_orm(r.provider),
            score=r.score,
            explanation=r.explanation
        ) for r in results[:5]],
        total_matches=len(results),
        search_quota_remaining=remaining - 1 if remaining > 0 else 0
    )


@router.post("/upload/initiate")
async def upload_initiate(
    filename: str,
    content_type: str,
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """Get presigned URL for document upload."""
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
    from app.services.file_service import extract_document_text
    text = await extract_document_text(key)
    return {"extracted_text": text[:5000], "key": key}


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


@router.post("/providers/claim-search")
async def claim_search(
    query: str,
    db: AsyncSession = Depends(get_db),
):
    """Search for providers to claim."""
    from sqlalchemy import select, or_
    from app.models.provider import Provider

    result = await db.execute(
        select(Provider).where(
            or_(
                Provider.name.ilike(f"%{query}%"),
                Provider.website.ilike(f"%{query}%"),
                Provider.city.ilike(f"%{query}%")
            )
        ).limit(10)
    )
    providers = result.scalars().all()

    return {
        "providers": [
            {"id": str(p.id), "name": p.name, "city": p.city, "state": p.state}
            for p in providers
        ]
    }
