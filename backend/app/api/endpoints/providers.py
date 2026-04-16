"""Provider API endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from typing import Any, Dict, List, Optional
import uuid
import asyncio
from app.tasks.search_tasks import generate_provider_embedding_async

from app.api.deps import get_db, get_current_active_user, require_role
from app.schemas.provider import (
    ProviderResponse, ProviderUpdateRequest,
    ProviderMembershipResponse, ProviderClaimRequest, ProviderClaimResponse,
)
from app.schemas.base import PagedResponse
from app.models.user import User
# Celery is optional - falls back gracefully if Redis not available
try:
    from app.core.celery import celery_app as _celery_app
except Exception:
    _celery_app = None
celery_app = _celery_app

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

@router.get("/provider/profile", response_model=ProviderResponse)
async def get_provider_profile(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Get current user's provider profile.

    Uses three fallback mechanisms:
    1. Explicit ProviderMembership (normal case)
    2. user.linked_provider_id (set during invite registration)
    3. RFQDispatch email_target matching (legacy fallback)
    """
    from app.models.provider import ProviderMembership, Provider, MembershipRole, MembershipStatus
    from app.models.rfq import RFQDispatch
    import logging
    _logger = logging.getLogger(__name__)

    # 1. Normal path: explicit membership exists
    result = await db.execute(
        select(ProviderMembership).where(ProviderMembership.user_id == current_user.id)
    )
    membership = result.scalar_one_or_none()

    if not membership:
        _logger.info(f"No membership for user {current_user.email}, checking linked_provider_id")

        # 2. Check linked_provider_id (set during invite registration)
        provider_id_to_link = getattr(current_user, 'linked_provider_id', None)

        if not provider_id_to_link:
            _logger.info(f"No linked_provider_id, checking RFQDispatch email match")
            # 3. Legacy fallback: RFQDispatch email_target matching
            dispatch_result = await db.execute(
                select(RFQDispatch).where(
                    RFQDispatch.email_target == current_user.email
                ).limit(1)
            )
            dispatch = dispatch_result.scalar_one_or_none()
            if dispatch:
                provider_id_to_link = dispatch.provider_id
                _logger.info(f"Found dispatch email match: provider_id={provider_id_to_link}")

        if provider_id_to_link:
            # Verify provider exists
            provider_check = await db.execute(
                select(Provider).where(Provider.id == provider_id_to_link)
            )
            if provider_check.scalar_one_or_none():
                # Check if membership already exists (race condition guard)
                existing_result = await db.execute(
                    select(ProviderMembership).where(
                        ProviderMembership.provider_id == provider_id_to_link,
                        ProviderMembership.user_id == current_user.id,
                    )
                )
                existing = existing_result.scalar_one_or_none()

                if not existing:
                    membership = ProviderMembership(
                        provider_id=provider_id_to_link,
                        user_id=current_user.id,
                        membership_role=MembershipRole.OWNER,
                        status=MembershipStatus.ACTIVE,
                        created_by=current_user.id,
                        invite_email=current_user.email,
                    )
                    db.add(membership)

                    if "provider" not in (current_user.roles or []):
                        current_user.roles = list(current_user.roles or []) + ["provider"]

                    await db.commit()
                    await db.refresh(membership)
                    _logger.info(f"Auto-created membership: user={current_user.id}, provider={provider_id_to_link}")
                else:
                    membership = existing
            else:
                _logger.warning(f"linked_provider_id {provider_id_to_link} does not exist in providers table")

        if not membership:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No provider profile found"
            )

    # Fetch the provider record with eager loading to avoid async lazy load crash
    result = await db.execute(
        select(Provider)
        .options(selectinload(Provider.memberships).selectinload(ProviderMembership.user))
        .where(Provider.id == membership.provider_id)
    )
    provider = result.scalar_one_or_none()
    if not provider:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Provider record not found"
        )
    return ProviderResponse.from_orm(provider)


@router.post("/provider/profile", response_model=ProviderResponse, status_code=status.HTTP_201_CREATED)
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

    # Re-query with eager loading to avoid async lazy load crash on memberships
    result2 = await db.execute(
        select(Provider)
        .options(selectinload(Provider.memberships).selectinload(ProviderMembership.user))
        .where(Provider.id == provider.id)
    )
    provider = result2.scalar_one()

    await generate_provider_embedding_async(str(provider.id))
    return ProviderResponse.from_orm(provider)


@router.patch("/provider/profile", response_model=ProviderResponse)
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

    # Re-query with eager loading to avoid async lazy load crash on memberships
    result3 = await db.execute(
        select(Provider)
        .options(selectinload(Provider.memberships).selectinload(ProviderMembership.user))
        .where(Provider.id == provider.id)
    )
    provider = result3.scalar_one()

    if data.business_description:
        await generate_provider_embedding_async(str(provider.id))

    return ProviderResponse.from_orm(provider)


@router.post("/provider/profile/request-rank-up")
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


# --------------- claim-search (with email_match flag) ---------------


@router.get("/provider/memberships")
async def get_provider_memberships(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Get current user's provider memberships."""
    from app.models.provider import ProviderMembership
    result = await db.execute(
        select(ProviderMembership).where(ProviderMembership.user_id == current_user.id)
    )
    memberships = result.scalars().all()
    return [{"id": str(m.id), "provider_id": m.provider_id, "membership_role": str(m.membership_role.value) if hasattr(m.membership_role, 'value') else str(m.membership_role), "status": str(m.status.value) if hasattr(m.status, 'value') else str(m.status)} for m in memberships]


@router.get("/providers/claim-search", response_model=List[ClaimSearchResult])
async def claim_search_providers(
    query: str = Query(..., min_length=2, description="Firm name to search"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Search providers by firm name for the claim flow.
    Returns email_match=True when the authenticated user email
    appears in provider.email_addresses (case-insensitive).
    """
    from app.models.provider import Provider, ProviderMembership
    pattern = "%" + query + "%"
    # Use selectinload to avoid async lazy load crash on memberships
    result = await db.execute(
        select(Provider)
        .options(selectinload(Provider.memberships).selectinload(ProviderMembership.user))
        .where(Provider.name.ilike(pattern))
        .limit(10)
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

@router.post("/provider-claims", response_model=ProviderClaimResponse, status_code=status.HTTP_201_CREATED)
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


@router.get("/provider-claims/me", response_model=List[ProviderClaimResponse])
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

@router.get("/admin/provider-claims", response_model=PagedResponse[ProviderClaimResponse])
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


@router.post("/admin/provider-claims/{claim_id}/approve")
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


@router.post("/admin/provider-claims/{claim_id}/reject")
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

@router.post("/providers/self-register/checkout")
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


@router.post("/providers/self-register/submit")
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
    await generate_provider_embedding_async(str(new_provider.id))

    return {"success": True, "provider_id": str(new_provider.id)}


# --------------- listing inquiry ($750 AI-assisted) ---------------

@router.post("/providers/listing-inquiry")
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


# ─── Full-Profile-Edit Endpoints (PART 4) ───────────────────────────────────

async def _provider_can_edit_profile(provider, db) -> bool:
    """Return True if provider is allowed to edit their full 17-field profile.

    Access is granted when EITHER:
    - provider.full_profile_edit_paid is True (one-time $500 payment), OR
    - provider has an active annual subscription (provider_annual type)

    Args:
        provider: Provider ORM object with .id and .full_profile_edit_paid fields.
        db: AsyncSession database session.

    Returns:
        True if profile editing is permitted.
    """
    # Fast path: one-time payment already unlocked
    if provider.full_profile_edit_paid:
        return True

    # Check active annual subscription
    from sqlalchemy import select
    from app.models.payment import Subscription
    from app.models.enums import SubscriptionStatus

    result = await db.execute(
        select(Subscription).where(
            Subscription.provider_id == provider.id,
            Subscription.subscription_type == "provider_annual",
            Subscription.subscription_status == SubscriptionStatus.ACTIVE,
        )
    )
    return result.scalar_one_or_none() is not None


EMBEDDING_FIELDS = {
    'firm_name', 'name', 'primary_specialty', 'business_description',
    'capabilities', 'specialties', 'software_tools',
    'proven_experience_notable_projects',
}


@router.get("/provider/profile/full-edit/status")
async def get_full_edit_status(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["provider"])),
):
    """Get full-profile-edit paid status for current provider."""
    from app.models.provider import ProviderMembership, Provider

    result = await db.execute(
        select(ProviderMembership).where(ProviderMembership.user_id == current_user.id)
    )
    membership = result.scalar_one_or_none()
    if not membership:
        return {"paid": False, "provider_id": None}

    result = await db.execute(
        select(Provider).where(Provider.id == membership.provider_id)
    )
    provider = result.scalar_one_or_none()
    if not provider:
        return {"paid": False, "provider_id": None}

    return {
        "paid": bool(provider.full_profile_edit_paid),
        "provider_id": str(provider.id),
    }


@router.post("/provider/profile/full-edit/checkout")
async def full_edit_checkout(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["provider"])),
):
    """Create Stripe PaymentIntent for full-profile-edit unlock ($500)."""
    from app.models.provider import ProviderMembership, Provider
    from app.services.payment_service import create_payment_intent

    result = await db.execute(
        select(ProviderMembership).where(ProviderMembership.user_id == current_user.id)
    )
    membership = result.scalar_one_or_none()
    if not membership:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No provider profile found")

    result = await db.execute(
        select(Provider).where(Provider.id == membership.provider_id)
    )
    provider = result.scalar_one_or_none()
    if not provider:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Provider record not found")

    if await _provider_can_edit_profile(provider, db):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Full profile edit already unlocked (or included in your annual subscription)")

    try:
        result = await create_payment_intent(
            db=db,
            purpose="full_profile_edit_unlock",
            amount=50000,
            currency="usd",
            user=current_user,
            related_entity_type="provider",
            related_id=uuid.uuid4(),
            metadata={
                "purpose": "full_profile_edit_unlock",
                "provider_id": str(provider.id),
            },
        )
        return result
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))


class FullProfileEditRequest(BaseModel):
    firm_name: Optional[str] = None
    name: Optional[str] = None
    business_description: Optional[str] = None
    primary_specialty: Optional[str] = None
    secondary_specialties: Optional[List[str]] = None
    capabilities: Optional[List[str]] = None
    specialties: Optional[List[str]] = None
    software_tools: Optional[List[str]] = None
    notable_clients: Optional[str] = None
    email_addresses: Optional[List[str]] = None
    certifications: Optional[List[str]] = None
    equipment: Optional[List[str]] = None
    proven_experience_notable_projects: Optional[List[str]] = None
    proven_experience_case_studies: Optional[List[str]] = None
    website: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    postal_code: Optional[str] = None
    team_summary: Optional[str] = None


@router.patch("/provider/profile/full-edit", response_model=ProviderResponse)
async def update_full_profile(
    data: FullProfileEditRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["provider"])),
):
    """Update provider full profile (requires full_profile_edit_paid == True)."""
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
    provider = result.scalar_one_or_none()
    if not provider:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Provider record not found")

    if not await _provider_can_edit_profile(provider, db):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Full profile edit not unlocked. Please purchase the $500 one-time edit or $1,000/year Annual Professional subscription.",
        )

    updated_fields = data.dict(exclude_unset=True)
    embedding_changed = False
    for field, value in updated_fields.items():
        setattr(provider, field, value)
        if field in EMBEDDING_FIELDS:
            embedding_changed = True

    await db.commit()

    # Re-query with eager loading to avoid async lazy load crash
    result2 = await db.execute(
        select(Provider)
        .options(selectinload(Provider.memberships).selectinload(ProviderMembership.user))
        .where(Provider.id == provider.id)
    )
    provider = result2.scalar_one()

    if embedding_changed:
        await generate_provider_embedding_async(str(provider.id))

    return ProviderResponse.from_orm(provider)


class CrawlWebsiteRequest(BaseModel):
    website_url: str


@router.post("/provider/profile/crawl-website")
async def crawl_provider_website(
    data: CrawlWebsiteRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["provider"])),
):
    """Queue website crawl and LLM extraction for provider profile auto-fill."""
    from app.models.provider import ProviderMembership, Provider

    if not data.website_url.startswith("http"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid URL: must start with http")

    result = await db.execute(
        select(ProviderMembership).where(ProviderMembership.user_id == current_user.id)
    )
    membership = result.scalar_one_or_none()
    if not membership:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No provider profile found")

    result = await db.execute(
        select(Provider).where(Provider.id == membership.provider_id)
    )
    provider = result.scalar_one_or_none()
    if not provider:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Provider record not found")

    if not await _provider_can_edit_profile(provider, db):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Full profile edit not unlocked. Please purchase the $500 one-time edit or $1,000/year Annual Professional subscription.",
        )

    if not celery_app:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Task queue not available")

    task = celery_app.send_task(
        "crawl_tasks.crawl_and_extract",
        args=[data.website_url, str(provider.id)],
    )
    return {"task_id": task.id, "status": "pending"}


@router.get("/provider/profile/crawl-status/{task_id}")
async def get_crawl_status(
    task_id: str,
    current_user: User = Depends(require_role(["provider"])),
):
    """Get crawl task status by task_id."""
    if not celery_app:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Task queue not available")

    try:
        from celery.result import AsyncResult
        async_result = AsyncResult(task_id, app=celery_app)
        state = async_result.state

        if state == "PENDING":
            return {"status": "pending", "data": None, "error": None}
        elif state == "STARTED":
            return {"status": "running", "data": None, "error": None}
        elif state == "SUCCESS":
            result = async_result.result or {}
            if isinstance(result, dict) and result.get("status") == "failed":
                return {"status": "failed", "data": None, "error": result.get("error")}
            data = result.get("data") if isinstance(result, dict) else result
            return {"status": "done", "data": data, "error": None}
        elif state == "FAILURE":
            return {"status": "failed", "data": None, "error": str(async_result.result)}
        else:
            return {"status": "pending", "data": None, "error": None}
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


# ─── Full-Profile-Edit Endpoints (PART 4) ───────────────────────────────────

EMBEDDING_FIELDS = {
    'firm_name', 'name', 'primary_specialty', 'business_description',
    'capabilities', 'specialties', 'software_tools',
    'proven_experience_notable_projects',
}

@router.get("/provider/profile/full-edit/status")
async def get_full_edit_status(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["provider"])),
):
    """Return whether the current provider has paid for full profile editing."""
    from sqlalchemy import select
    from app.models.provider import Provider, ProviderMembership
    result = await db.execute(
        select(Provider)
        .join(ProviderMembership, ProviderMembership.provider_id == Provider.id)
        .where(ProviderMembership.user_id == current_user.id)
        .limit(1)
    )
    provider = result.scalar_one_or_none()
    if not provider:
        return {"paid": False, "provider_id": None}
    return {"paid": bool(provider.full_profile_edit_paid), "provider_id": str(provider.id)}


@router.post("/provider/profile/full-edit/checkout")
async def full_edit_checkout(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["provider"])),
):
    """Create a Stripe PaymentIntent for the $500 full profile edit unlock."""
    import stripe
    from sqlalchemy import select
    from app.models.provider import Provider, ProviderMembership
    from app.models.payment import PaymentAttempt
    from app.services.config_service import RuntimeConfig
    import uuid as _uuid

    result = await db.execute(
        select(Provider)
        .join(ProviderMembership, ProviderMembership.provider_id == Provider.id)
        .where(ProviderMembership.user_id == current_user.id)
        .limit(1)
    )
    provider = result.scalar_one_or_none()
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")

    cfg = RuntimeConfig.get()
    stripe.api_key = cfg.get("STRIPE_SECRET_KEY", "")

    idempotency_key = f"full-profile-edit-{provider.id}"
    intent = stripe.PaymentIntent.create(
        amount=50000,
        currency="usd",
        metadata={
            "purpose": "full_profile_edit_unlock",
            "provider_id": str(provider.id),
        },
        idempotency_key=idempotency_key,
    )

    attempt = PaymentAttempt(
        provider_name="stripe",
        external_payment_id=intent["id"],
        purpose="full_profile_edit_unlock",
        related_entity_type="provider",
        related_entity_id=str(provider.id),
        amount=50000,
        currency="usd",
        payment_status="pending",
        idempotency_key=idempotency_key,
        initiated_by_user_id=current_user.id,
        metadata={"provider_id": str(provider.id)},
    )
    db.add(attempt)
    await db.commit()

    return {"client_secret": intent["client_secret"], "payment_intent_id": intent["id"]}


@router.patch("/provider/profile/full-edit")
async def save_full_profile_edit(
    data: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["provider"])),
):
    """Save all 17 fields for provider full profile edit. Requires full_profile_edit_paid=True."""
    from sqlalchemy import select
    from app.models.provider import Provider, ProviderMembership
    
    result = await db.execute(
        select(Provider)
        .join(ProviderMembership, ProviderMembership.provider_id == Provider.id)
        .where(ProviderMembership.user_id == current_user.id)
        .limit(1)
    )
    provider = result.scalar_one_or_none()
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")
    # Allow both one-time payment AND active annual subscription
    if not provider.full_profile_edit_paid:
        can_edit = await _provider_can_edit_profile(provider, db)
        if not can_edit:
            raise HTTPException(status_code=403, detail="Full profile edit requires the one-time unlock payment or an active Annual Pro subscription")

    ALLOWED_FIELDS = [
        'proven_experience_notable_projects', 'proven_experience_case_studies',
        'business_description', 'primary_specialty', 'capabilities', 'specialties',
        'software_tools', 'secondary_specialties', 'firm_name', 'name',
        'website', 'phone', 'email_addresses', 'city', 'state', 'address',
        'postal_code', 'certifications', 'notable_clients', 'equipment',
        'team_members', 'team_summary', 'projects',
    ]

    # Track if any embedding-relevant field changed
    embedding_changed = False
    for field, value in data.items():
        if field not in ALLOWED_FIELDS:
            continue
        old_val = getattr(provider, field, None)
        setattr(provider, field, value)
        if field in EMBEDDING_FIELDS and old_val != value:
            embedding_changed = True

    await db.commit()
    await db.refresh(provider)

    if embedding_changed:
        await generate_provider_embedding_async(str(provider.id))

    return {"message": "Profile updated", "embedding_queued": embedding_changed}


@router.post("/provider/profile/crawl-website")
async def crawl_provider_website(
    data: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["provider"])),
):
    """Queue a website crawl + LLM3 extraction task for the provider. Requires full_profile_edit_paid=True."""
    from sqlalchemy import select
    from app.models.provider import Provider, ProviderMembership
    from app.tasks.crawl_tasks import crawl_and_extract_task

    result = await db.execute(
        select(Provider)
        .join(ProviderMembership, ProviderMembership.provider_id == Provider.id)
        .where(ProviderMembership.user_id == current_user.id)
        .limit(1)
    )
    provider = result.scalar_one_or_none()
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")
    # Allow both one-time payment AND active annual subscription
    if not provider.full_profile_edit_paid:
        can_edit = await _provider_can_edit_profile(provider, db)
        if not can_edit:
            raise HTTPException(status_code=403, detail="Full profile edit requires the one-time unlock payment or an active Annual Pro subscription")

    website_url = data.get("website_url", "").strip()
    if not website_url or not website_url.startswith("http"):
        raise HTTPException(status_code=400, detail="Valid website URL required")

    task = crawl_and_extract_task.delay(website_url, str(provider.id))
    return {"task_id": task.id, "status": "pending"}


@router.get("/provider/profile/crawl-status/{task_id}")
async def get_crawl_status(
    task_id: str,
    current_user: User = Depends(require_role(["provider"])),
):
    """Poll the status of a website crawl task."""
    from celery.result import AsyncResult
    try:
        async_result = AsyncResult(task_id)
        state = async_result.state
        if state == "PENDING":
            return {"status": "pending", "data": None, "error": None}
        elif state == "STARTED":
            return {"status": "running", "data": None, "error": None}
        elif state == "SUCCESS":
            result = async_result.result or {}
            if isinstance(result, dict) and result.get("status") == "failed":
                return {"status": "failed", "data": None, "error": result.get("error")}
            data = result.get("data") if isinstance(result, dict) else result
            return {"status": "done", "data": data, "error": None}
        elif state == "FAILURE":
            return {"status": "failed", "data": None, "error": str(async_result.result)}
        else:
            return {"status": "pending", "data": None, "error": None}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
