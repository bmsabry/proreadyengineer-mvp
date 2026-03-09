"""Advertising API endpoints."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List

from app.api.deps import get_db, get_current_active_user, require_role
from app.schemas.advertising import (
    AdSlotResponse, AdvertisementResponse, AdCreateRequest, AdUpdateRequest,
)
from app.models.user import User

router = APIRouter()


@router.get("/ads/software-providers")
async def get_software_provider_ads(
    db: AsyncSession = Depends(get_db),
):
    """Get software provider advertisements."""
    from sqlalchemy import select
    from app.models.advertising import Advertisement, AdStatusEnum

    result = await db.execute(
        select(Advertisement).where(
            Advertisement.ad_status == AdStatusEnum.active
        )
    )
    ads = result.scalars().all()

    return {"advertisements": [AdvertisementResponse.from_orm(a) for a in ads]}


@router.get("/ads/featured-firms")
async def get_featured_firm_ads(
    db: AsyncSession = Depends(get_db),
):
    """Get featured firm advertisements."""
    from sqlalchemy import select
    from app.models.advertising import Advertisement, AdStatusEnum

    result = await db.execute(
        select(Advertisement).where(
            Advertisement.ad_status == AdStatusEnum.active
        )
    )
    ads = result.scalars().all()

    return {"advertisements": [AdvertisementResponse.from_orm(a) for a in ads]}


@router.post("/ads/checkout")
async def create_ad_checkout(
    slot_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["advertiser"])),
):
    """Create checkout for ad slot."""
    from app.services.payment_service import create_payment_intent

    intent = await create_payment_intent(
        db, "advertisement_subscription", 5000, "usd", current_user, slot_id  # $50/month
    )

    return {"client_secret": intent["client_secret"], "payment_intent_id": intent["id"]}


@router.get("/advertiser/ads/me", response_model=List[dict][AdvertisementResponse])
async def get_my_ads(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["advertiser"])),
):
    """Get current advertiser's ads."""
    from sqlalchemy import select
    from app.models.advertising import Advertisement

    result = await db.execute(
        select(Advertisement).where(Advertisement.advertiser_user_id == current_user.id)
    )
    ads = result.scalars().all()

    return [AdvertisementResponse.from_orm(a) for a in ads]


@router.post("/advertiser/ads/{ad_id}/asset/initiate")
async def initiate_ad_asset_upload(
    ad_id: str,
    filename: str,
    content_type: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["advertiser"])),
):
    """Get presigned URL for ad image upload."""
    from sqlalchemy import select
    from app.models.advertising import Advertisement
    from app.services.file_service import generate_upload_url
    import uuid

    # Verify ownership
    result = await db.execute(
        select(Advertisement).where(
            Advertisement.id == ad_id,
            Advertisement.advertiser_user_id == current_user.id
        )
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ad not found")

    key = f"ads/{ad_id}/assets/{uuid.uuid4()}/{filename}"
    url_data = generate_upload_url(key, content_type)

    return {"upload_url": url_data["url"], "fields": url_data["fields"], "key": key}


@router.post("/advertiser/ads/{ad_id}/asset/complete")
async def complete_ad_asset_upload(
    ad_id: str,
    key: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["advertiser"])),
):
    """Record uploaded ad asset."""
    from sqlalchemy import select
    from app.models.advertising import Advertisement

    result = await db.execute(
        select(Advertisement).where(
            Advertisement.id == ad_id,
            Advertisement.advertiser_user_id == current_user.id
        )
    )
    ad = result.scalar_one_or_none()

    if not ad:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ad not found")

    ad.image_s3_key = key
    await db.commit()

    return {"message": "Asset uploaded", "ad_id": ad_id}


@router.patch("/advertiser/ads/{ad_id}", response_model=AdvertisementResponse)
async def update_ad(
    ad_id: str,
    data: AdUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["advertiser"])),
):
    """Update advertisement."""
    from sqlalchemy import select
    from app.models.advertising import Advertisement

    result = await db.execute(
        select(Advertisement).where(
            Advertisement.id == ad_id,
            Advertisement.advertiser_user_id == current_user.id
        )
    )
    ad = result.scalar_one_or_none()

    if not ad:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ad not found")

    for field, value in data.dict(exclude_unset=True).items():
        setattr(ad, field, value)

    await db.commit()

    return AdvertisementResponse.from_orm(ad)
