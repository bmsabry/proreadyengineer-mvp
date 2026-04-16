"""Advertising API endpoints.

Supports:
  - Ad submission with LLM3-powered content extraction
  - LLM-powered ad search with relevance reordering
  - Click tracking + impression counting
  - Presigned upload for brochures/flyers
  - Advertiser self-service (my ads, update, asset upload)
  - Admin review/approval flow
  - Public ad listing (unlimited, paginated)
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_current_active_user, get_current_user_optional, require_role
from app.models.user import User
from app.schemas.advertising import (
    AdAssetUploadInitiateRequest,
    AdAssetUploadInitiateResponse,
    AdClickRequest,
    AdCreateRequest,
    AdSearchRequest,
    AdSearchResponse,
    AdSubmissionRequest,
    AdSubmissionResponse,
    AdUpdateRequest,
    AdminAdCreateRequest,
    AdminAdEditRequest,
    AdminAdReviewRequest,
    AdminAdReviewResponse,
    AdvertisementPublicResponse,
    AdvertisementResponse,
)

router = APIRouter()
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# LLM3 helpers for ad content extraction
# ---------------------------------------------------------------------------

async def _get_llm3_client(db: AsyncSession):
    """Get LLM3 client using runtime config (same pattern as search.py)."""
    from app.services.config_service import get_runtime_config as _get_runtime_config
    from openai import AsyncOpenAI

    config = await _get_runtime_config(db)
    doc_api_key = config.get("DOC_LLM_API_KEY") or ""
    if doc_api_key:
        llm_api_key = doc_api_key
        llm_base_url = config.get("DOC_LLM_API_BASE") or "https://api.openai.com/v1"
        llm_model = config.get("DOC_LLM_MODEL") or "gpt-4o-mini"
    else:
        llm_api_key = config.get("OPENAI_API_KEY") or ""
        llm_base_url = config.get("OPENAI_API_BASE") or "https://api.deepinfra.com/v1/openai"
        llm_model = config.get("OPENAI_LLM_MODEL") or "moonshotai/Kimi-K2.5"

    client = AsyncOpenAI(api_key=llm_api_key, base_url=llm_base_url)
    return client, llm_model


async def _extract_ad_content(
    db: AsyncSession,
    website_text: str | None,
    description_text: str | None,
    page_type: str,
) -> Dict[str, Any]:
    """Use LLM3 to extract structured ad content from materials."""
    combined_text = ""
    if website_text:
        combined_text += f"=== WEBSITE CONTENT ===\n{website_text}\n\n"
    if description_text:
        combined_text += f"=== UPLOADED MATERIALS / DESCRIPTION ===\n{description_text}\n\n"

    if not combined_text.strip():
        raise ValueError("No content provided for ad extraction")

    # Truncate to 80k chars
    combined_text = combined_text[:80000]

    ad_type_context = (
        "a software product/tool advertisement" if page_type == "software-providers"
        else "an engineering firm advertisement"
    )

    prompt = f"""You are creating {ad_type_context} from the following content.

{combined_text}

Extract and return a JSON object with these fields:
{{
  "headline": "Compelling 5-10 word headline that captures the core value proposition",
  "tagline": "One punchy sentence (max 15 words) — the hook that grabs attention",
  "value_proposition": "2-3 sentences explaining what makes this offering unique and valuable",
  "specialties": ["list", "of", "key", "specialties", "or", "features"],
  "capabilities": ["list", "of", "specific", "capabilities", "or", "services"],
  "proof_points": ["list of credibility signals: certifications, years in business, notable clients, project counts, etc."],
  "cta_label": "Call-to-action button text (e.g. 'Get a Quote', 'Try Free', 'Learn More')",
  "industry_keywords": ["relevant", "industry", "keywords", "for", "search", "matching"],
  "contact_info": {{
    "phone": "phone number if found",
    "email": "email if found",
    "location": "city, state if found"
  }},
  "company_name": "Official company or product name",
  "promotional_summary": "A 2-4 sentence promotional paragraph suitable for an ad card"
}}

IMPORTANT:
- Make the headline action-oriented and benefit-focused
- The tagline should create urgency or curiosity
- Proof points should be specific and quantifiable where possible
- Industry keywords should be comprehensive for search matching
- Return ONLY valid JSON. No markdown wrapping."""

    client, model = await _get_llm3_client(db)
    response = await client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
        temperature=0.2,
    )
    content = response.choices[0].message.content
    return json.loads(content)


async def _fetch_full_website_for_ad(url: str) -> str:
    """Crawl the full website — same approach as admin 'add firm' workflow."""
    from app.api.endpoints.admin import _admin_fetch_website_text
    return await _admin_fetch_website_text(url)


# ---------------------------------------------------------------------------
# Ad Submission (new workflow)
# ---------------------------------------------------------------------------

async def _process_ad_in_background(ad_id: uuid.UUID, source_url: Optional[str],
                                     description_text: Optional[str], page_type: str) -> None:
    """Background task: crawl website + LLM extraction, then update ad record."""
    from app.db.session import AsyncSessionLocal
    from app.models.advertising import Advertisement
    from app.models.enums import AdStatus

    async with AsyncSessionLocal() as bg_db:
        try:
            # Crawl the full website — all pages, same as admin "add firm"
            website_text: str | None = None
            if source_url:
                logger.info("Ad bg starting crawl ad_id=%s url=%s", ad_id, source_url)
                try:
                    raw = await _fetch_full_website_for_ad(source_url)
                    website_text = raw if raw and raw.strip() else None
                    logger.info("Ad bg crawl done ad_id=%s url=%s chars=%d",
                                ad_id, source_url, len(website_text or ""))
                except Exception as exc:
                    logger.warning("Ad bg crawl failed ad_id=%s url=%s err=%s", ad_id, source_url, exc)

            # If crawl returned nothing but we have a description, use that alone
            if not website_text and description_text:
                logger.info("Ad %s crawl empty — using description_text only", ad_id)

            if not website_text and not description_text:
                logger.error("Ad %s has no content (url=%s) — marking rejected", ad_id, source_url)
                await bg_db.execute(
                    update(Advertisement)
                    .where(Advertisement.id == ad_id)
                    .values(ad_status=AdStatus.REJECTED,
                            title="Content extraction failed — please re-submit with a description")
                )
                await bg_db.commit()
                return

            # LLM3 extraction — full website content → ad fields
            extracted = await _extract_ad_content(bg_db, website_text=website_text,
                                                   description_text=description_text, page_type=page_type)
            headline = extracted.get("headline", "Advertisement")
            promo_summary = extracted.get("promotional_summary") or extracted.get("value_proposition", "")

            await bg_db.execute(
                update(Advertisement)
                .where(Advertisement.id == ad_id)
                .values(
                    ad_status=AdStatus.PENDING_REVIEW,
                    title=headline[:200],
                    promotional_text=promo_summary[:2000] if promo_summary else None,
                    llm_extracted_content=extracted,
                )
            )
            await bg_db.commit()
            logger.info("Ad %s processing complete → pending_review", ad_id)

        except Exception as exc:
            logger.exception("Ad background processing failed ad_id=%s err=%s", ad_id, exc)


@router.post("/ads/submit", response_model=AdSubmissionResponse)
async def submit_ad(
    data: AdSubmissionRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Submit a new advertisement for review.

    Creates the ad record immediately (status=processing) and returns success
    right away. The full website crawl + LLM3 extraction run in a background
    task — same deep crawl as admin "add firm". Ad moves to pending_review
    when processing completes.
    """
    from app.models.advertising import Advertisement
    from app.models.enums import AdStatus
    from app.models.provider import Provider, ProviderMembership

    # Resolve provider membership
    provider_id: int | None = None
    membership_result = await db.execute(
        select(ProviderMembership.provider_id).where(
            ProviderMembership.user_id == current_user.id,
            ProviderMembership.status == "active",
        ).limit(1)
    )
    membership_row = membership_result.scalar_one_or_none()
    if membership_row:
        provider_id = membership_row

    # Resolve source URL
    source_url = data.website_url
    if source_url and not source_url.startswith("http"):
        source_url = "https://" + source_url

    if not source_url and provider_id:
        provider_result = await db.execute(
            select(Provider.website).where(Provider.id == provider_id)
        )
        existing_website = provider_result.scalar_one_or_none()
        if existing_website:
            source_url = existing_website
            if not source_url.startswith("http"):
                source_url = "https://" + source_url

    if not source_url and not data.description_text:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Please provide a website URL or a description to generate your ad.",
        )

    # Create the ad record immediately with PROCESSING status
    ad_id = uuid.uuid4()
    ad = Advertisement(
        id=ad_id,
        advertiser_user_id=current_user.id,
        provider_id=provider_id,
        page_type=data.page_type,
        title="Generating your ad…",
        ad_status=AdStatus.PROCESSING,
        source_website_url=source_url,
        outbound_url=data.outbound_url or source_url,
        uploaded_materials_s3_keys=data.uploaded_material_keys,
        click_count=0,
        impression_count=0,
    )
    db.add(ad)

    if "advertiser" not in (current_user.roles or []):
        current_user.roles = list(current_user.roles or []) + ["advertiser"]

    await db.commit()

    # Kick off crawl + LLM in background — full website read like admin "add firm"
    background_tasks.add_task(
        _process_ad_in_background,
        ad_id=ad_id,
        source_url=source_url,
        description_text=data.description_text,
        page_type=data.page_type,
    )

    return AdSubmissionResponse(
        ad_id=ad_id,
        ad_status=AdStatus.PROCESSING,
        title="Generating your ad…",
        promotional_text=None,
        llm_extracted_content=None,
        message="Your ad is being generated. Our AI is reading your website now. This takes 1-2 minutes — you can close this page and check back shortly.",
    )


# ---------------------------------------------------------------------------
# Presigned upload for ad materials (brochures, flyers, PDFs)
# ---------------------------------------------------------------------------

@router.post("/ads/materials/upload-url", response_model=AdAssetUploadInitiateResponse)
async def get_material_upload_url(
    data: AdAssetUploadInitiateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Get a presigned S3 URL for uploading ad materials (brochures, flyers, etc.)."""
    from app.services.file_service import generate_upload_url

    key = f"ad-materials/{current_user.id}/{uuid.uuid4()}/{data.filename}"
    url_data = generate_upload_url(key, data.mime_type, max_file_size=data.file_size_bytes)

    return AdAssetUploadInitiateResponse(
        upload_url=url_data["url"],
        fields=url_data.get("fields", {}),
        s3_key=key,
    )


# ---------------------------------------------------------------------------
# Public ad listing (unlimited, paginated)
# ---------------------------------------------------------------------------

@router.get("/ads/software-providers")
async def get_software_provider_ads(
    page: int = Query(1, ge=1),
    page_size: int = Query(24, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """Get active software provider advertisements — unlimited, paginated."""
    from app.models.advertising import Advertisement
    from app.models.enums import AdStatus

    # Count total
    count_result = await db.execute(
        select(func.count()).select_from(Advertisement).where(
            Advertisement.ad_status == AdStatus.ACTIVE,
            Advertisement.page_type == "software-providers",
        )
    )
    total = count_result.scalar() or 0

    # Fetch page
    result = await db.execute(
        select(Advertisement).where(
            Advertisement.ad_status == AdStatus.ACTIVE,
            Advertisement.page_type == "software-providers",
        ).order_by(Advertisement.started_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    ads = result.scalars().all()

    # Increment impression counts
    ad_ids = [a.id for a in ads]
    if ad_ids:
        await db.execute(
            update(Advertisement)
            .where(Advertisement.id.in_(ad_ids))
            .values(impression_count=Advertisement.impression_count + 1)
        )
        await db.commit()

    return {
        "advertisements": [_to_public_response(a) for a in ads],
        "total_count": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/ads/featured-firms")
async def get_featured_firm_ads(
    page: int = Query(1, ge=1),
    page_size: int = Query(24, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """Get active featured firm advertisements — unlimited, paginated."""
    from app.models.advertising import Advertisement
    from app.models.enums import AdStatus

    count_result = await db.execute(
        select(func.count()).select_from(Advertisement).where(
            Advertisement.ad_status == AdStatus.ACTIVE,
            Advertisement.page_type == "featured-firms",
        )
    )
    total = count_result.scalar() or 0

    result = await db.execute(
        select(Advertisement).where(
            Advertisement.ad_status == AdStatus.ACTIVE,
            Advertisement.page_type == "featured-firms",
        ).order_by(Advertisement.started_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    ads = result.scalars().all()

    ad_ids = [a.id for a in ads]
    if ad_ids:
        await db.execute(
            update(Advertisement)
            .where(Advertisement.id.in_(ad_ids))
            .values(impression_count=Advertisement.impression_count + 1)
        )
        await db.commit()

    return {
        "advertisements": [_to_public_response(a) for a in ads],
        "total_count": total,
        "page": page,
        "page_size": page_size,
    }


# ---------------------------------------------------------------------------
# LLM-powered ad search
# ---------------------------------------------------------------------------

@router.post("/ads/search", response_model=AdSearchResponse)
async def search_ads(
    data: AdSearchRequest,
    db: AsyncSession = Depends(get_db),
):
    """Search active ads using LLM to reorder by relevance to the query.

    The LLM receives the query and all active ad summaries, then returns
    a ranked ordering based on service/capability matching.
    """
    from app.models.advertising import Advertisement
    from app.models.enums import AdStatus

    # Determine page_type filter
    conditions = [Advertisement.ad_status == AdStatus.ACTIVE]
    if data.page_type:
        conditions.append(Advertisement.page_type == data.page_type)

    result = await db.execute(
        select(Advertisement).where(*conditions)
    )
    all_ads = result.scalars().all()

    if not all_ads:
        return AdSearchResponse(query=data.query, advertisements=[], total_count=0)

    # Build summaries for LLM ranking
    ad_summaries = []
    for i, ad in enumerate(all_ads):
        content = ad.llm_extracted_content or {}
        summary = {
            "index": i,
            "title": ad.title,
            "specialties": content.get("specialties", []),
            "capabilities": content.get("capabilities", []),
            "industry_keywords": content.get("industry_keywords", []),
            "value_proposition": content.get("value_proposition", ""),
        }
        ad_summaries.append(summary)

    # Ask LLM to rank
    try:
        client, model = await _get_llm3_client(db)
        ranking_prompt = f"""You are ranking advertisements by relevance to a user's search query.

Search query: "{data.query}"

Advertisements:
{json.dumps(ad_summaries, indent=2)}

Return a JSON object with a single key "ranked_indices" containing an array of the advertisement indices
ordered from most relevant to least relevant based on how well they match the search query.
Only include ads that have at least some relevance to the query.

Example: {{"ranked_indices": [2, 0, 5, 1]}}

Return ONLY valid JSON."""

        response = await client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": ranking_prompt}],
            response_format={"type": "json_object"},
            temperature=0.1,
        )
        ranking = json.loads(response.choices[0].message.content)
        ranked_indices = ranking.get("ranked_indices", list(range(len(all_ads))))
    except Exception as exc:
        logger.warning("Ad search LLM ranking failed, using default order: %s", exc)
        ranked_indices = list(range(len(all_ads)))

    # Build ordered response
    ranked_ads = []
    for idx in ranked_indices:
        if 0 <= idx < len(all_ads):
            ranked_ads.append(all_ads[idx])

    # Increment impressions on returned ads
    shown_ids = [a.id for a in ranked_ads]
    if shown_ids:
        await db.execute(
            update(Advertisement)
            .where(Advertisement.id.in_(shown_ids))
            .values(impression_count=Advertisement.impression_count + 1)
        )
        await db.commit()

    return AdSearchResponse(
        query=data.query,
        advertisements=[_to_public_response(a) for a in ranked_ads],
        total_count=len(ranked_ads),
    )


# ---------------------------------------------------------------------------
# Click tracking
# ---------------------------------------------------------------------------

@router.post("/ads/{ad_id}/click")
async def record_ad_click(
    ad_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Record an ad click. Returns the outbound URL for redirect."""
    from app.models.advertising import Advertisement

    result = await db.execute(
        select(Advertisement).where(Advertisement.id == ad_id)
    )
    ad = result.scalar_one_or_none()
    if not ad:
        raise HTTPException(status_code=404, detail="Ad not found")

    ad.click_count = (ad.click_count or 0) + 1
    await db.commit()

    return {"outbound_url": ad.outbound_url, "click_count": ad.click_count}


# ---------------------------------------------------------------------------
# Advertiser self-service
# ---------------------------------------------------------------------------

@router.get("/advertiser/ads/me", response_model=List[AdvertisementResponse])
async def get_my_ads(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Get current user's advertisements."""
    from app.models.advertising import Advertisement

    result = await db.execute(
        select(Advertisement)
        .where(Advertisement.advertiser_user_id == current_user.id)
        .order_by(Advertisement.created_at.desc())
    )
    ads = result.scalars().all()

    return [AdvertisementResponse.model_validate(a) for a in ads]


@router.patch("/advertiser/ads/{ad_id}", response_model=AdvertisementResponse)
async def update_ad(
    ad_id: str,
    data: AdUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Update advertisement content."""
    from app.models.advertising import Advertisement

    result = await db.execute(
        select(Advertisement).where(
            Advertisement.id == ad_id,
            Advertisement.advertiser_user_id == current_user.id,
        )
    )
    ad = result.scalar_one_or_none()
    if not ad:
        raise HTTPException(status_code=404, detail="Ad not found")

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(ad, field, value)

    await db.commit()
    await db.refresh(ad)

    return AdvertisementResponse.model_validate(ad)


@router.post("/advertiser/ads/{ad_id}/asset/initiate")
async def initiate_ad_asset_upload(
    ad_id: str,
    filename: str,
    content_type: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Get presigned URL for ad image upload."""
    from app.models.advertising import Advertisement
    from app.services.file_service import generate_upload_url

    result = await db.execute(
        select(Advertisement).where(
            Advertisement.id == ad_id,
            Advertisement.advertiser_user_id == current_user.id,
        )
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Ad not found")

    key = f"ads/{ad_id}/assets/{uuid.uuid4()}/{filename}"
    url_data = generate_upload_url(key, content_type)

    return {"upload_url": url_data["url"], "fields": url_data["fields"], "key": key}


@router.post("/advertiser/ads/{ad_id}/asset/complete")
async def complete_ad_asset_upload(
    ad_id: str,
    key: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Record uploaded ad asset."""
    from app.models.advertising import Advertisement

    result = await db.execute(
        select(Advertisement).where(
            Advertisement.id == ad_id,
            Advertisement.advertiser_user_id == current_user.id,
        )
    )
    ad = result.scalar_one_or_none()
    if not ad:
        raise HTTPException(status_code=404, detail="Ad not found")

    ad.image_s3_key = key
    await db.commit()

    return {"message": "Asset uploaded", "ad_id": ad_id}


# ---------------------------------------------------------------------------
# Ad checkout (Stripe subscription for $50/month)
# ---------------------------------------------------------------------------

@router.post("/ads/checkout")
async def create_ad_checkout(
    ad_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Create Stripe checkout for an approved ad ($50/month subscription)."""
    from app.models.advertising import Advertisement
    from app.models.enums import AdStatus

    result = await db.execute(
        select(Advertisement).where(
            Advertisement.id == ad_id,
            Advertisement.advertiser_user_id == current_user.id,
        )
    )
    ad = result.scalar_one_or_none()
    if not ad:
        raise HTTPException(status_code=404, detail="Ad not found")

    if ad.ad_status != AdStatus.ACTIVE and ad.ad_status != AdStatus.RESERVED_CHECKOUT_PENDING:
        raise HTTPException(
            status_code=400,
            detail=f"Ad must be approved before checkout. Current status: {ad.ad_status}",
        )

    from app.services.payment_service import create_payment_intent
    intent = await create_payment_intent(
        db, "advertisement_subscription", 5000, "usd", current_user, str(ad.id)
    )

    return {"client_secret": intent["client_secret"], "payment_intent_id": intent["id"]}


# ---------------------------------------------------------------------------
# Admin: Ad Review/Approval
# ---------------------------------------------------------------------------

@router.get("/admin/ads/pending", response_model=List[AdvertisementResponse])
async def get_pending_ads(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin"])),
):
    """Get all ads pending admin review."""
    from app.models.advertising import Advertisement
    from app.models.enums import AdStatus

    result = await db.execute(
        select(Advertisement)
        .where(Advertisement.ad_status == AdStatus.PENDING_REVIEW)
        .order_by(Advertisement.created_at.asc())
    )
    ads = result.scalars().all()
    return [AdvertisementResponse.model_validate(a) for a in ads]


@router.post("/admin/ads/{ad_id}/review", response_model=AdminAdReviewResponse)
async def review_ad(
    ad_id: str,
    data: AdminAdReviewRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin"])),
):
    """Admin approves or rejects an ad submission."""
    from app.models.advertising import Advertisement
    from app.models.enums import AdStatus

    result = await db.execute(
        select(Advertisement).where(Advertisement.id == ad_id)
    )
    ad = result.scalar_one_or_none()
    if not ad:
        raise HTTPException(status_code=404, detail="Ad not found")

    if ad.ad_status != AdStatus.PENDING_REVIEW:
        raise HTTPException(
            status_code=400,
            detail=f"Ad is not pending review. Current status: {ad.ad_status}",
        )

    now = datetime.utcnow()

    if data.action == "approve":
        ad.ad_status = AdStatus.ACTIVE
        ad.started_at = now
        message = "Ad approved and is now live."
    else:
        ad.ad_status = AdStatus.REJECTED
        message = "Ad has been rejected."

    ad.admin_review_notes = data.notes
    ad.reviewed_by_user_id = current_user.id
    ad.reviewed_at = now

    await db.commit()
    await db.refresh(ad)

    # TODO: Send email notification to advertiser

    return AdminAdReviewResponse(
        ad_id=ad.id,
        ad_status=ad.ad_status,
        reviewed_at=ad.reviewed_at,
        message=message,
    )


# ---------------------------------------------------------------------------
# Admin: Create Ad on behalf of a provider
# ---------------------------------------------------------------------------

@router.post("/admin/ads/create", response_model=AdSubmissionResponse)
async def admin_create_ad(
    data: AdminAdCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin"])),
):
    """Admin creates an advertisement for a registered provider.

    Uses LLM3 to scrape the provider's website and/or supplied text to
    generate structured ad content. The ad is auto-approved (active).
    """
    from app.models.advertising import Advertisement
    from app.models.enums import AdStatus
    from app.models.provider import Provider

    # Verify provider exists
    provider_result = await db.execute(
        select(Provider).where(Provider.id == data.provider_id)
    )
    provider = provider_result.scalar_one_or_none()
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")

    # Gather content
    website_text: str | None = None
    source_url = data.website_url or provider.website

    if source_url:
        if not source_url.startswith("http"):
            source_url = "https://" + source_url
        try:
            website_text = await _fetch_full_website_for_ad(source_url)
        except Exception as exc:
            logger.warning("Admin ad website fetch failed url=%s err=%s", source_url, exc)

    if not website_text and not data.description_text:
        raise HTTPException(
            status_code=422,
            detail="Provider has no website and no description text was provided.",
        )

    # LLM3 extraction
    try:
        extracted = await _extract_ad_content(
            db,
            website_text=website_text,
            description_text=data.description_text,
            page_type=data.page_type,
        )
    except Exception as exc:
        logger.error("Admin ad LLM extraction failed: %s", exc)
        raise HTTPException(status_code=422, detail=f"LLM extraction failed: {exc}")

    headline = extracted.get("headline", provider.name or "Advertisement")
    promo_summary = extracted.get("promotional_summary") or extracted.get("value_proposition", "")

    # Find the user associated with this provider (if any)
    from app.models.provider import ProviderMembership
    membership_result = await db.execute(
        select(ProviderMembership.user_id).where(
            ProviderMembership.provider_id == data.provider_id,
            ProviderMembership.status == "active",
        ).limit(1)
    )
    advertiser_user_id = membership_result.scalar_one_or_none() or current_user.id

    now = datetime.utcnow()
    ad = Advertisement(
        id=uuid.uuid4(),
        advertiser_user_id=advertiser_user_id,
        provider_id=data.provider_id,
        page_type=data.page_type,
        title=headline[:200],
        promotional_text=promo_summary[:2000] if promo_summary else None,
        outbound_url=data.outbound_url or source_url,
        ad_status=AdStatus.ACTIVE,  # Admin-created → auto-approved
        llm_extracted_content=extracted,
        source_website_url=source_url,
        click_count=0,
        impression_count=0,
        reviewed_by_user_id=current_user.id,
        reviewed_at=now,
        started_at=now,
        admin_review_notes="Auto-approved: created by admin",
    )
    db.add(ad)
    await db.commit()
    await db.refresh(ad)

    return AdSubmissionResponse(
        ad_id=ad.id,
        ad_status=ad.ad_status,
        title=ad.title,
        promotional_text=ad.promotional_text,
        llm_extracted_content=extracted,
        message="Ad created and auto-approved by admin.",
    )


# ---------------------------------------------------------------------------
# Admin: Edit Ad
# ---------------------------------------------------------------------------

@router.patch("/admin/ads/{ad_id}", response_model=AdvertisementResponse)
async def admin_edit_ad(
    ad_id: str,
    data: AdminAdEditRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin"])),
):
    """Admin edits any field on an advertisement."""
    from app.models.advertising import Advertisement

    result = await db.execute(
        select(Advertisement).where(Advertisement.id == ad_id)
    )
    ad = result.scalar_one_or_none()
    if not ad:
        raise HTTPException(status_code=404, detail="Ad not found")

    update_data = data.model_dump(exclude_unset=True)

    # Handle status changes
    if "ad_status" in update_data:
        new_status = update_data["ad_status"]
        if new_status == "active" and not ad.started_at:
            ad.started_at = datetime.utcnow()

    for field, value in update_data.items():
        setattr(ad, field, value)

    await db.commit()
    await db.refresh(ad)

    return AdvertisementResponse.model_validate(ad)


# ---------------------------------------------------------------------------
# Admin: Delete Ad
# ---------------------------------------------------------------------------

@router.delete("/admin/ads/{ad_id}")
async def admin_delete_ad(
    ad_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin"])),
):
    """Admin permanently deletes an advertisement."""
    from app.models.advertising import Advertisement

    result = await db.execute(
        select(Advertisement).where(Advertisement.id == ad_id)
    )
    ad = result.scalar_one_or_none()
    if not ad:
        raise HTTPException(status_code=404, detail="Ad not found")

    await db.delete(ad)
    await db.commit()

    return {"message": "Ad deleted", "ad_id": ad_id}


# ---------------------------------------------------------------------------
# Admin: Reactivate Ad
# ---------------------------------------------------------------------------

@router.post("/admin/ads/{ad_id}/reactivate", response_model=AdvertisementResponse)
async def admin_reactivate_ad(
    ad_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin"])),
):
    """Admin reactivates a paused, cancelled, or rejected ad."""
    from app.models.advertising import Advertisement
    from app.models.enums import AdStatus

    result = await db.execute(
        select(Advertisement).where(Advertisement.id == ad_id)
    )
    ad = result.scalar_one_or_none()
    if not ad:
        raise HTTPException(status_code=404, detail="Ad not found")

    if ad.ad_status == AdStatus.ACTIVE:
        raise HTTPException(status_code=400, detail="Ad is already active")

    ad.ad_status = AdStatus.ACTIVE
    if not ad.started_at:
        ad.started_at = datetime.utcnow()
    ad.ended_at = None
    ad.reviewed_by_user_id = current_user.id
    ad.reviewed_at = datetime.utcnow()
    ad.admin_review_notes = (ad.admin_review_notes or "") + f"\nReactivated by admin at {datetime.utcnow().isoformat()}"

    await db.commit()
    await db.refresh(ad)

    return AdvertisementResponse.model_validate(ad)


# ---------------------------------------------------------------------------
# Admin: Ad Analytics
# ---------------------------------------------------------------------------

@router.get("/admin/ads/analytics")
async def ad_analytics(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin"])),
):
    """Ad performance analytics for admin dashboard."""
    from app.models.advertising import Advertisement
    from app.models.enums import AdStatus

    # Total counts by status
    status_counts = {}
    for st in AdStatus:
        count_result = await db.execute(
            select(func.count()).select_from(Advertisement).where(
                Advertisement.ad_status == st.value
            )
        )
        cnt = count_result.scalar() or 0
        if cnt > 0:
            status_counts[st.value] = cnt

    # Total clicks and impressions
    totals_result = await db.execute(
        select(
            func.sum(Advertisement.click_count),
            func.sum(Advertisement.impression_count),
        )
    )
    totals = totals_result.one()
    total_clicks = totals[0] or 0
    total_impressions = totals[1] or 0

    return {
        "status_counts": status_counts,
        "total_clicks": total_clicks,
        "total_impressions": total_impressions,
        "ctr": round(total_clicks / total_impressions * 100, 2) if total_impressions > 0 else 0,
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _to_public_response(ad) -> dict:
    """Convert Advertisement model to public response dict."""
    from app.services.file_service import generate_download_url

    image_url = None
    if ad.image_s3_key:
        try:
            image_url = generate_download_url(ad.image_s3_key)
        except Exception:
            pass

    content = ad.llm_extracted_content or {}

    return {
        "id": str(ad.id),
        "title": ad.title,
        "promotional_text": ad.promotional_text,
        "outbound_url": ad.outbound_url,
        "image_url": image_url,
        "optional_price_text": ad.optional_price_text,
        "provider_id": ad.provider_id,
        "page_type": ad.page_type,
        "llm_extracted_content": content,
        "click_count": ad.click_count or 0,
        "impression_count": ad.impression_count or 0,
    }
