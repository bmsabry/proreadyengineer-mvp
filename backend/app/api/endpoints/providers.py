"""Provider API endpoints."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List

from app.api.deps import get_db, get_current_active_user, require_role
from app.schemas.provider import (
    ProviderResponse, ProviderUpdateRequest,
    ProviderMembershipResponse, ProviderClaimRequest, ProviderClaimResponse,
)
from app.schemas.base import PagedResponse
from app.models.user import User
from app.services.search_service import generate_embedding
from app.core.celery import celery_app

router = APIRouter()


@router.get("/profile", response_model=ProviderResponse)
async def get_provider_profile(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Get current user's provider profile."""
    from sqlalchemy import select
    from app.models.provider import ProviderMembership, Provider

    # Get user's provider membership
    result = await db.execute(
        select(ProviderMembership).where(ProviderMembership.user_id == current_user.id)
    )
    membership = result.scalar_one_or_none()

    if not membership:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No provider profile found")

    # Get provider
    result = await db.execute(
        select(Provider).where(Provider.id == membership.provider_id)
    )
    provider = result.scalar_one()

    return ProviderResponse.from_orm(provider)


@router.post("/profile", response_model=ProviderResponse, status_code=status.HTTP_201_CREATED)
async def create_provider_profile(
    data: ProviderUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["provider"])),
):
    """Create a new provider profile."""
    from app.models.provider import Provider, ProviderMembership
    import uuid

    provider = Provider(
        id=uuid.uuid4(),
        name=data.name,
        website=data.website,
        phone=data.phone,
        address=data.address,
        city=data.city,
        state=data.state,
        postal_code=data.postal_code,
        primary_specialty=data.primary_specialty,
        business_description=data.business_description,
        tier="E",  # Start at lowest tier
        is_active=True,
    )
    db.add(provider)

    # Create membership
    membership = ProviderMembership(
        provider_id=provider.id,
        user_id=current_user.id,
        membership_role="owner",
        status="approved",
    )
    db.add(membership)
    await db.commit()

    # Queue embedding generation
    celery_app.send_task("app.tasks.search_tasks.generate_provider_embedding_task", args=[str(provider.id)])

    return ProviderResponse.from_orm(provider)


@router.patch("/profile", response_model=ProviderResponse)
async def update_provider_profile(
    data: ProviderUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["provider"])),
):
    """Update provider profile (subscription required)."""
    from sqlalchemy import select
    from app.models.provider import ProviderMembership, Provider, ProviderSubscription
    from app.models.payment import SubscriptionStatusEnum

    # Check subscription
    result = await db.execute(
        select(ProviderSubscription).where(
            ProviderSubscription.provider_id == ProviderMembership.provider_id,
            ProviderMembership.user_id == current_user.id,
            ProviderSubscription.status == SubscriptionStatusEnum.active
        )
    )
    subscription = result.scalar_one_or_none()

    if not subscription:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Active subscription required to edit profile"
        )

    # Get provider
    result = await db.execute(
        select(ProviderMembership).where(ProviderMembership.user_id == current_user.id)
    )
    membership = result.scalar_one()

    result = await db.execute(
        select(Provider).where(Provider.id == membership.provider_id)
    )
    provider = result.scalar_one()

    # Update fields
    for field, value in data.dict(exclude_unset=True).items():
        setattr(provider, field, value)

    await db.commit()

    # Re-generate embedding if description changed
    if data.business_description:
        celery_app.send_task("app.tasks.search_tasks.generate_provider_embedding_task", args=[str(provider.id)])

    return ProviderResponse.from_orm(provider)


@router.post("/profile/request-rank-up")
async def request_rank_up(
    reason: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["provider"])),
):
    """Request tier evaluation/rank up."""
    from sqlalchemy import select
    from app.models.provider import ProviderMembership, Provider, TierEvaluationRequest
    import uuid
    from datetime import datetime

    result = await db.execute(
        select(ProviderMembership).where(ProviderMembership.user_id == current_user.id)
    )
    membership = result.scalar_one()

    result = await db.execute(
        select(Provider).where(Provider.id == membership.provider_id)
    )
    provider = result.scalar_one()

    request = TierEvaluationRequest(
        id=uuid.uuid4(),
        provider_id=provider.id,
        requested_by_user_id=current_user.id,
        current_tier=provider.tier,
        requested_reason=reason,
        status="pending",
        created_at=datetime.utcnow(),
    )
    db.add(request)
    await db.commit()

    return {"message": "Rank up request submitted", "request_id": str(request.id)}


@router.get("/memberships", response_model=List[ProviderMembershipResponse])
async def get_memberships(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Get user's provider memberships."""
    from sqlalchemy import select
    from app.models.provider import ProviderMembership

    result = await db.execute(
        select(ProviderMembership).where(ProviderMembership.user_id == current_user.id)
    )
    memberships = result.scalars().all()

    return [ProviderMembershipResponse.from_orm(m) for m in memberships]


@router.post("/claims", response_model=ProviderClaimResponse, status_code=status.HTTP_201_CREATED)
async def create_claim_request(
    data: ProviderClaimRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["provider"])),
):
    """Submit a claim request for existing provider."""
    from sqlalchemy import select
    from app.models.provider import ProviderClaimRequest, Provider
    import uuid
    from datetime import datetime, timedelta

    # Verify provider exists
    result = await db.execute(select(Provider).where(Provider.id == data.provider_id))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Provider not found")

    claim = ProviderClaimRequest(
        id=uuid.uuid4(),
        provider_id=data.provider_id,
        claimant_user_id=current_user.id,
        status="pending",
        proof_type=data.proof_type,
        proof_payload=data.proof_payload,
        submitted_notes=data.notes,
        created_at=datetime.utcnow(),
        expires_at=datetime.utcnow() + timedelta(days=7),
    )
    db.add(claim)
    await db.commit()

    return ProviderClaimResponse.from_orm(claim)


@router.get("/claims/me", response_model=List[ProviderClaimResponse])
async def get_my_claims(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Get current user's claim requests."""
    from sqlalchemy import select
    from app.models.provider import ProviderClaimRequest

    result = await db.execute(
        select(ProviderClaimRequest).where(ProviderClaimRequest.claimant_user_id == current_user.id)
    )
    claims = result.scalars().all()

    return [ProviderClaimResponse.from_orm(c) for c in claims]


# Admin endpoints for claims
@router.get("/admin/claims", response_model=PagedResponse[ProviderClaimResponse])
async def admin_list_claims(
    status: str = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin"])),
):
    """Admin: List all claim requests."""
    from sqlalchemy import select
    from app.models.provider import ProviderClaimRequest

    query = select(ProviderClaimRequest)
    if status:
        query = query.where(ProviderClaimRequest.status == status)

    result = await db.execute(query)
    claims = result.scalars().all()

    return PagedResponse(
        items=[ProviderClaimResponse.from_orm(c) for c in claims],
        total=len(claims),
        page=1,
        size=len(claims)
    )


@router.post("/admin/claims/{claim_id}/approve")
async def admin_approve_claim(
    claim_id: str,
    notes: str = "",
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin"])),
):
    """Admin: Approve a claim request."""
    from sqlalchemy import select
    from app.models.provider import ProviderClaimRequest, ProviderMembership
    from datetime import datetime
    import uuid

    result = await db.execute(
        select(ProviderClaimRequest).where(ProviderClaimRequest.id == claim_id)
    )
    claim = result.scalar_one_or_none()

    if not claim:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Claim not found")

    claim.status = "approved"
    claim.reviewed_by = current_user.id
    claim.reviewed_at = datetime.utcnow()
    claim.admin_review_notes = notes

    # Create membership
    membership = ProviderMembership(
        id=uuid.uuid4(),
        provider_id=claim.provider_id,
        user_id=claim.claimant_user_id,
        membership_role="owner",
        status="approved",
        created_by=current_user.id,
    )
    db.add(membership)
    await db.commit()

    return {"message": "Claim approved", "membership_id": str(membership.id)}


@router.post("/admin/claims/{claim_id}/reject")
async def admin_reject_claim(
    claim_id: str,
    notes: str = "",
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin"])),
):
    """Admin: Reject a claim request."""
    from sqlalchemy import select
    from app.models.provider import ProviderClaimRequest
    from datetime import datetime

    result = await db.execute(
        select(ProviderClaimRequest).where(ProviderClaimRequest.id == claim_id)
    )
    claim = result.scalar_one_or_none()

    if not claim:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Claim not found")

    claim.status = "rejected"
    claim.reviewed_by = current_user.id
    claim.reviewed_at = datetime.utcnow()
    claim.admin_review_notes = notes
    await db.commit()

    return {"message": "Claim rejected"}
