"""Factory functions for creating test data.

Provides convenient functions to create test entities with sensible defaults.
All functions accept optional kwargs to override default values.
"""

import uuid
from datetime import datetime, timedelta
from typing import Any, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models import (
    User,
    Provider,
    ProviderMembership,
    ProviderClaimRequest,
    RFQ,
    RFQFile,
    RFQMatch,
    Quote,
    QuoteStatus,
    PaymentAttempt,
    PaymentStatus,
    Subscription,
    SubscriptionStatus,
    SubscriptionType,
    NdaStatus,
    RfqStatus,
    ClaimStatus,
    MembershipRole,
    MembershipStatus,
)
from app.services.auth_service import hash_password


# =============================================================================
# User Factories
# =============================================================================

async def create_test_user(
    db: AsyncSession,
    email: str = "test@example.com",
    password: str = "testpassword123",
    roles: List[str] = None,
    first_name: str = "Test",
    last_name: str = "User",
    is_super_admin: bool = False,
    **kwargs
) -> User:
    """Create a test user with specified attributes.
    
    Args:
        db: Database session.
        email: User email address.
        password: Plain text password (will be hashed).
        roles: List of user roles (default: ["customer"]).
        first_name: User's first name.
        last_name: User's last name.
        is_super_admin: Whether user is super admin.
        **kwargs: Additional User model attributes.
    
    Returns:
        User: Created user instance.
    """
    if roles is None:
        roles = ["customer"]
    
    # Check if user with email already exists
    result = await db.execute(select(User).where(User.email == email.lower()))
    existing = result.scalar_one_or_none()
    if existing:
        return existing
    
    user = User(
        id=uuid.uuid4(),
        email=email.lower(),
        password_hash=hash_password(password),
        roles=roles,
        first_name=first_name,
        last_name=last_name,
        is_super_admin=is_super_admin,
        **kwargs
    )
    
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def create_customer(db: AsyncSession, **kwargs) -> User:
    """Create a test customer user."""
    defaults = {
        "email": f"customer_{uuid.uuid4().hex[:8]}@test.com",
        "roles": ["customer"],
        "first_name": "Test",
        "last_name": "Customer",
    }
    defaults.update(kwargs)
    return await create_test_user(db, **defaults)


async def create_provider_user(db: AsyncSession, **kwargs) -> User:
    """Create a test provider user."""
    defaults = {
        "email": f"provider_{uuid.uuid4().hex[:8]}@test.com",
        "roles": ["provider"],
        "first_name": "Test",
        "last_name": "Provider",
    }
    defaults.update(kwargs)
    return await create_test_user(db, **defaults)


async def create_admin(db: AsyncSession, **kwargs) -> User:
    """Create a test admin user."""
    defaults = {
        "email": f"admin_{uuid.uuid4().hex[:8]}@test.com",
        "roles": ["admin"],
        "first_name": "Test",
        "last_name": "Admin",
        "is_super_admin": True,
        "can_review_claims": True,
        "can_moderate_providers": True,
        "can_moderate_ads": True,
        "can_manage_refunds": True,
        "can_override_rfq_status": True,
        "can_review_tier_requests": True,
    }
    defaults.update(kwargs)
    return await create_test_user(db, **defaults)


async def create_advertiser(db: AsyncSession, **kwargs) -> User:
    """Create a test advertiser user."""
    defaults = {
        "email": f"advertiser_{uuid.uuid4().hex[:8]}@test.com",
        "roles": ["advertiser"],
        "first_name": "Test",
        "last_name": "Advertiser",
    }
    defaults.update(kwargs)
    return await create_test_user(db, **defaults)


# =============================================================================
# Provider Factories
# =============================================================================

async def create_test_provider(
    db: AsyncSession,
    name: str = "Test Engineering Solutions",
    business_description: str = "Test engineering service provider specializing in mechanical design.",
    primary_specialty: str = "Mechanical Engineering",
    business_evaluation_tier: str = "B",
    email_addresses: List[str] = None,
    capabilities: List[str] = None,
    specialties: List[str] = None,
    software_tools: List[str] = None,
    embedding: List[float] = None,
    **kwargs
) -> Provider:
    """Create a test provider with specified attributes.
    
    Args:
        db: Database session.
        name: Provider company name.
        business_description: Company description.
        primary_specialty: Primary specialty.
        business_evaluation_tier: Tier rating (A, B, C, D, E).
        email_addresses: List of contact emails.
        capabilities: List of capabilities.
        specialties: List of specialties.
        software_tools: List of software tools used.
        embedding: Vector embedding for description.
        **kwargs: Additional Provider model attributes.
    
    Returns:
        Provider: Created provider instance.
    """
    if email_addresses is None:
        email_addresses = [f"contact_{uuid.uuid4().hex[:8]}@provider.com"]
    
    if capabilities is None:
        capabilities = ["FEA", "CAD Design", "Prototyping"]
    
    if specialties is None:
        specialties = ["Mechanical Engineering", "Structural Analysis"]
    
    if software_tools is None:
        software_tools = ["SolidWorks", "ANSYS", "AutoCAD"]
    
    if embedding is None:
        # Generate dummy 1536-dim embedding
        embedding = [0.1] * 1536
    
    provider = Provider(
        name=name,
        business_description=business_description,
        primary_specialty=primary_specialty,
        business_evaluation_tier=business_evaluation_tier,
        email_addresses=email_addresses,
        capabilities=capabilities,
        specialties=specialties,
        software_tools=software_tools,
        embedding=embedding,
        embedding_model="text-embedding-3-small",
        embedding_version="1.0",
        embedding_generated_at=datetime.utcnow(),
        **kwargs
    )
    
    db.add(provider)
    await db.commit()
    await db.refresh(provider)
    return provider


async def create_test_provider_membership(
    db: AsyncSession,
    provider_id: int,
    user_id: uuid.UUID,
    role: MembershipRole = MembershipRole.OWNER,
    status: MembershipStatus = MembershipStatus.ACTIVE,
    **kwargs
) -> ProviderMembership:
    """Create a test provider membership.
    
    Args:
        db: Database session.
        provider_id: Provider ID.
        user_id: User ID.
        role: Membership role (owner, editor, billing_manager, viewer).
        status: Membership status.
        **kwargs: Additional ProviderMembership model attributes.
    
    Returns:
        ProviderMembership: Created membership instance.
    """
    membership = ProviderMembership(
        provider_id=provider_id,
        user_id=user_id,
        membership_role=role,
        status=status,
        created_by=user_id,
        **kwargs
    )
    
    db.add(membership)
    await db.commit()
    await db.refresh(membership)
    return membership


async def create_test_claim_request(
    db: AsyncSession,
    provider_id: int,
    claimant_user_id: uuid.UUID,
    status: ClaimStatus = ClaimStatus.PENDING,
    proof_type: str = "email_domain",
    proof_payload: dict = None,
    **kwargs
) -> ProviderClaimRequest:
    """Create a test provider claim request.
    
    Args:
        db: Database session.
        provider_id: Provider ID being claimed.
        claimant_user_id: User making the claim.
        status: Claim status.
        proof_type: Type of proof submitted.
        proof_payload: Proof data.
        **kwargs: Additional ProviderClaimRequest model attributes.
    
    Returns:
        ProviderClaimRequest: Created claim request instance.
    """
    if proof_payload is None:
        proof_payload = {"email": f"user@company.com", "domain_verified": True}
    
    claim = ProviderClaimRequest(
        provider_id=provider_id,
        claimant_user_id=claimant_user_id,
        status=status,
        proof_type=proof_type,
        proof_payload=proof_payload,
        submitted_notes="Please approve my claim",
        **kwargs
    )
    
    db.add(claim)
    await db.commit()
    await db.refresh(claim)
    return claim


# =============================================================================
# RFQ Factories
# =============================================================================

async def create_test_rfq(
    db: AsyncSession,
    customer_id: Optional[uuid.UUID] = None,
    customer_email: str = "rfq_customer@test.com",
    business_name: str = "Test Customer Corp",
    contact_name: str = "John Doe",
    project_description: str = "Need structural analysis for aerospace component.",
    urgency: str = "High",
    tollgate_phases: List[str] = None,
    nda_required: bool = False,
    rfq_status: RfqStatus = RfqStatus.DRAFT,
    **kwargs
) -> RFQ:
    """Create a test RFQ with specified attributes.
    
    Args:
        db: Database session.
        customer_id: Customer user ID (optional for guest RFQs).
        customer_email: Customer email address.
        business_name: Customer business name.
        contact_name: Contact person name.
        project_description: Project description.
        urgency: Urgency level (High, Intermediate, Low).
        tollgate_phases: Selected tollgate phases.
        nda_required: Whether NDA is required.
        rfq_status: RFQ status.
        **kwargs: Additional RFQ model attributes.
    
    Returns:
        RFQ: Created RFQ instance.
    """
    if tollgate_phases is None:
        tollgate_phases = ["TG1", "TG3"]
    
    rfq = RFQ(
        id=uuid.uuid4(),
        customer_user_id=customer_id,
        customer_email=customer_email,
        business_name=business_name,
        contact_name=contact_name,
        project_description=project_description,
        urgency=urgency,
        tollgate_phases=tollgate_phases,
        nda_required=nda_required,
        rfq_status=rfq_status,
        quote_count=0,
        is_closed=False,
        **kwargs
    )
    
    db.add(rfq)
    await db.commit()
    await db.refresh(rfq)
    return rfq


async def create_test_rfq_file(
    db: AsyncSession,
    rfq_id: uuid.UUID,
    s3_key: str = "uploads/rfq/test_file.pdf",
    original_filename: str = "specifications.pdf",
    mime_type: str = "application/pdf",
    file_size_bytes: int = 1024000,
    uploaded_by_user_id: Optional[uuid.UUID] = None,
    **kwargs
) -> RFQFile:
    """Create a test RFQ file attachment.
    
    Args:
        db: Database session.
        rfq_id: RFQ ID.
        s3_key: S3 object key.
        original_filename: Original filename.
        mime_type: MIME type.
        file_size_bytes: File size in bytes.
        uploaded_by_user_id: User who uploaded (optional).
        **kwargs: Additional RFQFile model attributes.
    
    Returns:
        RFQFile: Created RFQ file instance.
    """
    rfq_file = RFQFile(
        rfq_id=rfq_id,
        s3_key=s3_key,
        original_filename=original_filename,
        mime_type=mime_type,
        file_size_bytes=file_size_bytes,
        uploaded_by_user_id=uploaded_by_user_id,
        **kwargs
    )
    
    db.add(rfq_file)
    await db.commit()
    await db.refresh(rfq_file)
    return rfq_file


async def create_test_rfq_match(
    db: AsyncSession,
    rfq_id: uuid.UUID,
    provider_id: int,
    rank_position: int = 1,
    composite_score: int = 85,
    specialty_score: int = 20,
    capabilities_score: int = 40,
    tier_score: int = 25,
    scoring_inputs: dict = None,
    **kwargs
) -> RFQMatch:
    """Create a test RFQ match record.
    
    Args:
        db: Database session.
        rfq_id: RFQ ID.
        provider_id: Provider ID.
        rank_position: Match rank position.
        composite_score: Total match score (0-100).
        specialty_score: Specialty match component.
        capabilities_score: Capabilities match component.
        tier_score: Tier score component.
        scoring_inputs: Raw scoring inputs JSON.
        **kwargs: Additional RFQMatch model attributes.
    
    Returns:
        RFQMatch: Created RFQ match instance.
    """
    if scoring_inputs is None:
        scoring_inputs = {
            "primary_specialty": "Mechanical Engineering",
            "capabilities": ["FEA", "CAD"],
            "tier": "B",
            "intent_specialty": "structural analysis",
            "intent_capabilities": ["FEA"],
        }
    
    match = RFQMatch(
        rfq_id=rfq_id,
        provider_id=provider_id,
        rank_position=rank_position,
        composite_score=composite_score,
        specialty_score=specialty_score,
        capabilities_score=capabilities_score,
        tier_score=tier_score,
        scoring_inputs=scoring_inputs,
        is_dispatched=False,
        **kwargs
    )
    
    db.add(match)
    await db.commit()
    await db.refresh(match)
    return match


# =============================================================================
# Quote Factories
# =============================================================================

async def create_test_quote(
    db: AsyncSession,
    rfq_id: uuid.UUID,
    provider_id: int,
    submitter_user_id: uuid.UUID,
    quote_status: QuoteStatus = QuoteStatus.DRAFT,
    rough_price_min: Optional[int] = 10000,
    rough_price_max: Optional[int] = 25000,
    currency: str = "USD",
    turnaround_estimate_text: str = "4-6 weeks",
    assumptions_text: str = "Assumes standard materials and standard tolerances.",
    scope_notes: str = "Full scope to be defined after NDA signing.",
    **kwargs
) -> Quote:
    """Create a test quote with specified attributes.
    
    Args:
        db: Database session.
        rfq_id: RFQ ID.
        provider_id: Provider ID.
        submitter_user_id: User submitting the quote.
        quote_status: Quote status.
        rough_price_min: Minimum price estimate.
        rough_price_max: Maximum price estimate.
        currency: Currency code.
        turnaround_estimate_text: Estimated timeline.
        assumptions_text: Quote assumptions.
        scope_notes: Scope limitations.
        **kwargs: Additional Quote model attributes.
    
    Returns:
        Quote: Created quote instance.
    """
    quote = Quote(
        id=uuid.uuid4(),
        rfq_id=rfq_id,
        provider_id=provider_id,
        submitter_user_id=submitter_user_id,
        quote_status=quote_status,
        rough_price_min=rough_price_min,
        rough_price_max=rough_price_max,
        currency=currency,
        turnaround_estimate_text=turnaround_estimate_text,
        assumptions_text=assumptions_text,
        scope_notes=scope_notes,
        **kwargs
    )
    
    db.add(quote)
    await db.commit()
    await db.refresh(quote)
    return quote


# =============================================================================
# Payment Factories
# =============================================================================

async def create_test_payment_attempt(
    db: AsyncSession,
    provider_name: str = "stripe",
    external_payment_id: str = None,
    external_checkout_id: str = None,
    purpose: str = "rfq_unlock",
    related_entity_type: str = "rfq",
    related_entity_id: uuid.UUID = None,
    amount: int = 1000,
    currency: str = "usd",
    payment_status: PaymentStatus = PaymentStatus.INITIATED,
    idempotency_key: str = None,
    initiated_by_user_id: Optional[uuid.UUID] = None,
    **kwargs
) -> PaymentAttempt:
    """Create a test payment attempt.
    
    Args:
        db: Database session.
        provider_name: Payment provider (stripe, paypal).
        external_payment_id: Provider's payment ID.
        external_checkout_id: Provider's checkout/session ID.
        purpose: Payment purpose.
        related_entity_type: Type of entity being paid for.
        related_entity_id: ID of related entity.
        amount: Amount in cents.
        currency: Currency code.
        payment_status: Payment status.
        idempotency_key: Unique idempotency key.
        initiated_by_user_id: User who initiated payment.
        **kwargs: Additional PaymentAttempt model attributes.
    
    Returns:
        PaymentAttempt: Created payment attempt instance.
    """
    if external_payment_id is None:
        external_payment_id = f"pi_test_{uuid.uuid4().hex[:12]}"
    
    if external_checkout_id is None:
        external_checkout_id = f"secret_{uuid.uuid4().hex[:12]}"
    
    if related_entity_id is None:
        related_entity_id = uuid.uuid4()
    
    if idempotency_key is None:
        idempotency_key = f"idemp_{uuid.uuid4().hex[:12]}"
    
    payment = PaymentAttempt(
        provider_name=provider_name,
        external_payment_id=external_payment_id,
        external_checkout_id=external_checkout_id,
        purpose=purpose,
        related_entity_type=related_entity_type,
        related_entity_id=related_entity_id,
        amount=amount,
        currency=currency,
        payment_status=payment_status,
        idempotency_key=idempotency_key,
        initiated_by_user_id=initiated_by_user_id,
        initiated_at=datetime.utcnow(),
        **kwargs
    )
    
    db.add(payment)
    await db.commit()
    await db.refresh(payment)
    return payment


async def create_test_subscription(
    db: AsyncSession,
    user_id: Optional[uuid.UUID] = None,
    provider_id: Optional[int] = None,
    external_subscription_id: str = None,
    subscription_type: SubscriptionType = SubscriptionType.PROVIDER_PROFILE,
    subscription_status: SubscriptionStatus = SubscriptionStatus.ACTIVE,
    **kwargs
) -> Subscription:
    """Create a test subscription.
    
    Args:
        db: Database session.
        user_id: Subscriber user ID.
        provider_id: Related provider ID (for provider subscriptions).
        external_subscription_id: Provider's subscription ID.
        subscription_type: Type of subscription.
        subscription_status: Subscription status.
        **kwargs: Additional Subscription model attributes.
    
    Returns:
        Subscription: Created subscription instance.
    """
    if external_subscription_id is None:
        external_subscription_id = f"sub_test_{uuid.uuid4().hex[:12]}"
    
    now = datetime.utcnow()
    subscription = Subscription(
        user_id=user_id,
        provider_id=provider_id,
        external_subscription_id=external_subscription_id,
        subscription_type=subscription_type,
        subscription_status=subscription_status,
        current_period_start=now,
        current_period_end=now + timedelta(days=30),
        **kwargs
    )
    
    db.add(subscription)
    await db.commit()
    await db.refresh(subscription)
    return subscription
