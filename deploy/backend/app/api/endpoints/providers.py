"""Provider API endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Any, Dict, List, Optional
import uuid

from app.api.deps import get_db, get_current_active_user, require_role
from app.schemas.provider import (
    ProviderResponse, ProviderUpdateRequest,
    ProviderMembershipResponse, ProviderClaimRequest, ProviderClaimResponse,
)
from app.schemas.base import PagedResponse
from app.models.user import User
from app.core.celery import celery_app

router = APIRouter()


class ClaimSearchResult(ProviderResponse):
    """ProviderResponse extended with email_match flag for the claim flow."""
    email_match: bool = False


class SelfRegisterProviderRequest(BaseModel):
    """Body for the $100 self-service provider listing."""
    name: str
    city: Optional[str] = None
    state: Optional[str] = None
    website: Optional[str] = None
    phone: Optional[str] = None
    primary_specialty: Optional[str] = None
    business_description: Optional[str] = None
    proven_experience_notable_projects: Optional[List[str]] = None
    payment_intent_id: str


class ListingInquiryRequest(BaseModel):
    """Body for the $750 AI-assisted listing inquiry."""
    firm_name: str
    firm_description: str
    contact_name: str


# --------------- profile ---------------

@router.get("/profile", response_model=ProviderResponse)
async def get_provider_profile(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Get current user's provider profile."""
    from app.models.provider import ProviderMembership, Provider

    result = await db.execute(
        select(ProviderMembership).where(ProviderMembership.user_id == current_user.id)
    )
    membership = result.scalar_one_or_none()
    if not membership:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No provider profile found")

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
        tier="E",
        is_active=True,
    )
    db.add(provider)

    membership = ProviderMembership(
        provider_id=provider.id,
        user_id=current_user.id,
        membership_role="owner",
        status="approved",
    )
    db.add(membership)
    await db.commit()

    celery_app.send_task("app.tasks.search_tasks.generate_provider_embedding_task", args=[str(provider.id)])
    return ProviderResponse.from_orm(provider)


@router.patch("/profile", response_model=ProviderResponse)
async def update_provider_profile(
    data: ProviderUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["provider"])),
):
    """Update provider profile (subscription required)."""
    from app.models.provider import ProviderMembership, Provider, ProviderSubscription
    from app.models.payment import SubscriptionStatusEnum

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

    result = await db.execute(
        select(ProviderMembership).where(ProviderMembership.user_id == current_user.id)
    )
    membership = result.scalar_one()

    result = await db.execute(
        select(Provider).where(Provider.id == membership.provider_id)
    )
    provider = result.scalar_one()

    for field, value in data.dict(exclude_unset=True).items():
        setattr(provider, field, value)
    await db.commit()

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
    from app.models.provider import ProviderMembership, Provider, TierEvaluationRequest
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


# --------------- claim-search (NEW: with email_match flag) ---------------

@router.get("/claim-search", response_model=List[ClaimSearchResult])
async def claim_search_providers(
    query: str = Query(..., min_length=2, description="Firm name to search"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Search providers by firm name for the claim flow.
    Returns email_match=True when the authenticated user email
    appears in provider.email_addresses (case-insensitive).
    """
    from app.models.provider import Provider
    pattern = "%" + query + "%"
    result = await db.execute(
        select(Provider).where(Provider.name.ilike(pattern)).limit(10)
    )
    providers = result.scalars().all()
    user_email = (current_user.email or "").strip().lower()
    response: List[ClaimSearchResult] = []
    for p in providers:
        base = ProviderResponse.from_orm(p).dict()
        provider_emails = [e.strip().lower() for e in (p.email_addresses or []) if e]
        base["email_match"] = bool(user_email and user_email in provider_emails)
        response.append(ClaimSearchResult(**base))
    return response


# --------------- claims (UPDATED: email validation gate) ---------------

@router.post("/claims", response_model=ProviderClaimResponse, status_code=status.HTTP_201_CREATED)
async def create_claim_request(
    data: ProviderClaimRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["provider"])),
):
    """Submit a claim for an existing provider record.
    If provider has email_addresses set, the claimant email must
    appear in that list (case-insensitive) or 403 is returned.
    """
    from app.models.provider import ProviderClaimRequest as ClaimModel, Provider
    from datetime import datetime, timedelta

    result = await db.execute(select(Provider).where(Provider.id == data.provider_id))
    provider = result.scalar_one_or_none()
    if not provider:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Provider not found")

    # --- email validation gate ---
    if provider.email_addresses:
        provider_emails = [e.strip().lower() for e in provider.email_addresses if e]
        user_email = (current_user.email or "").strip().lower()
        if provider_emails and user_email not in provider_emails:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    "Your account email does not match any email address on file for this firm. "
                    "Please contact support or use the self-service listing option."
                ),
            )

    claim = ClaimModel(
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
    from app.models.provider import ProviderClaimRequest

    result = await db.execute(
        select(ProviderClaimRequest).where(ProviderClaimRequest.claimant_user_id == current_user.id)
    )
    claims = result.scalars().all()
    return [ProviderClaimResponse.from_orm(c) for c in claims]


# --------------- admin claims ---------------

@router.get("/admin/claims", response_model=PagedResponse[ProviderClaimResponse])
async def admin_list_claims(
    status: str = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin"])),
):
    """Admin: List all claim requests."""
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
    """Admin: Approve a claim request and create membership."""
    from app.models.provider import ProviderClaimRequest, ProviderMembership
    from datetime import datetime

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


# --------------- self-register ($100 one-time) ---------------

@router.post("/self-register/checkout")
async def self_register_provider_checkout(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Create a Stripe PaymentIntent for self-service provider listing ($100)."""
    from app.services.payment_service import create_payment_intent
    pending_id = uuid.uuid4()
    try:
        result = await create_payment_intent(
            db=db,
            purpose="provider_listing",
            amount=10000,
            currency="usd",
            user=current_user,
            related_entity_type="provider_listing",
            related_id=pending_id,
            metadata={"user_id": str(current_user.id)},
        )
        return result
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/self-register/submit")
async def self_register_provider_submit(
    data: SelfRegisterProviderRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Submit self-service provider listing after Stripe payment confirmation."""
    from app.models.payment import PaymentAttempt
    from app.models.provider import Provider, ProviderMembership
    from datetime import datetime

    # Verify payment record exists for this user
    payment_result = await db.execute(
        select(PaymentAttempt).where(
            PaymentAttempt.external_payment_id == data.payment_intent_id,
            PaymentAttempt.initiated_by_user_id == current_user.id,
            PaymentAttempt.purpose == "provider_listing",
        )
    )
    payment = payment_result.scalar_one_or_none()
    if not payment:
        raise HTTPException(status_code=400, detail="Payment not found or does not belong to your account")

    # Create provider record
    new_provider = Provider(
        id=uuid.uuid4(),
        name=data.name,
        city=data.city,
        state=data.state,
        website=data.website,
        phone=data.phone,
        primary_specialty=data.primary_specialty,
        business_description=data.business_description,
        proven_experience_notable_projects=data.proven_experience_notable_projects or [],
        tier="E",
        email_addresses=[current_user.email] if current_user.email else [],
        is_active=True,
    )
    db.add(new_provider)
    await db.flush()

    # Create owner membership
    membership = ProviderMembership(
        id=uuid.uuid4(),
        provider_id=new_provider.id,
        user_id=current_user.id,
        membership_role="owner",
        status="approved",
        created_by=current_user.id,
    )
    db.add(membership)

    # Add provider role if not present
    if "provider" not in (current_user.roles or []):
        current_user.roles = list(current_user.roles or []) + ["provider"]

    await db.commit()
    await db.refresh(new_provider)

    # Queue embedding generation async
    celery_app.send_task(
        "app.tasks.search_tasks.generate_provider_embedding_task",
        args=[str(new_provider.id)]
    )

    return {"success": True, "provider_id": str(new_provider.id)}


# --------------- listing inquiry ($750 AI-assisted) ---------------

@router.post("/listing-inquiry")
async def submit_listing_inquiry(
    data: ListingInquiryRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Submit an AI-assisted listing inquiry ($750 option)."""
    from app.services.email_service import send_listing_inquiry_email
    await send_listing_inquiry_email(
        db=db,
        user_email=current_user.email,
        user_name=data.contact_name,
        firm_name=data.firm_name,
        firm_description=data.firm_description,
    )
    return {
        "success": True,
        "message": "Your inquiry has been received. We will contact you within 1 business day.",
    }
