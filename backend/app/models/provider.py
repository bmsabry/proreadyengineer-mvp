"""Provider directory and ownership models."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from sqlalchemy import (
    Boolean,
    JSON,

    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.types import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from pgvector.sqlalchemy import Vector

from app.models.base import Base
from app.models.enums import ClaimStatus, MembershipRole, MembershipStatus

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.rfq import RFQ, RFQDispatch, RFQMatch, RFQUnlock
    from app.models.quote import Quote
    from app.models.payment import Subscription
    from app.models.admin import AuditLog, TierEvaluationRequest
    from app.models.advertising import Advertisement
    from app.models.nda import RFQNDA


class Provider(Base):
    """Provider directory migrated from SQLite companies table.
    
    Preserves all 53 columns from source companies table (6,766 records).
    """
    
    __tablename__ = "providers"
    
    # Primary Key (preserving SQLite INTEGER PK)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    
    # Basic Info (from companies table)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    firm_name: Mapped[str] = mapped_column(Text, nullable=False)
    website: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    address: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    city: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    state: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    postal_code: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Google Places Data
    rating: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(3, 2), nullable=True
    )
    review_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    place_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    search_query: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    search_city: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Classification Flags (from companies)
    is_engineering_service: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    is_mechanical_focus: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    classification_confidence: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )
    classification_reasoning: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )
    
    # Specialties (from companies)
    primary_specialty: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    secondary_specialties: Mapped[Optional[List[str]]] = mapped_column(
        JSON, nullable=True
    )
    
    # Crawl Status (from companies)
    homepage_crawl_status: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )
    homepage_file: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    homepage_content_size: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True
    )
    deep_crawl_status: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    deep_crawl_page_count: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True
    )
    deep_crawl_content_size: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True
    )
    
    # AI-Enriched Content (from companies)
    business_description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    capabilities: Mapped[Optional[List[str]]] = mapped_column(
        JSON, nullable=True
    )
    specialties: Mapped[Optional[List[str]]] = mapped_column(
        JSON, nullable=True
    )
    software_tools: Mapped[Optional[List[str]]] = mapped_column(
        JSON, nullable=True
    )
    notable_clients: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    email_addresses: Mapped[Optional[List[str]]] = mapped_column(
        JSON, nullable=True
    )
    certifications: Mapped[Optional[List[str]]] = mapped_column(
        JSON, nullable=True
    )
    equipment: Mapped[Optional[List[str]]] = mapped_column(
        JSON, nullable=True
    )
    
    # Business Evaluation (from companies)
    business_evaluation_tier: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )
    business_evaluation_years_in_business: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True
    )
    business_evaluation_employee_count: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )
    
    # Proven Experience (from companies)
    proven_experience_project_count: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True
    )
    proven_experience_case_studies: Mapped[Optional[List[str]]] = mapped_column(
        JSON, nullable=True
    )
    proven_experience_industries_served: Mapped[Optional[List[str]]] = mapped_column(
        JSON, nullable=True
    )
    proven_experience_years_in_business: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True
    )
    proven_experience_notable_projects: Mapped[Optional[List[str]]] = mapped_column(
        JSON, nullable=True
    )
    
    # Online Presence (from companies)
    online_presence_youtube_channel: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )
    online_presence_linkedin_url: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )
    online_presence_yelp_url: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )
    online_presence_review_count: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True
    )
    online_presence_average_rating: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(3, 2), nullable=True
    )
    online_presence_reputation_summary: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )
    
    # Team & Projects (from companies) - Complex nested structures
    team_members: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON, nullable=True
    )
    team_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    projects: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    
    # New MVP Fields - Claim Status
    claim_status: Mapped[Optional[ClaimStatus]] = mapped_column(
        String, nullable=True
    )
    claimed_by_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    claimed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    
    # Embedding Fields (Section 11.2)
    embedding: Mapped[Optional[Any]] = mapped_column(
        Vector(1536), nullable=True
    )
    embedding_model: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    embedding_generated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    embedding_version: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    

    @property
    def tier(self) -> "Optional[str]":
        """Alias for business_evaluation_tier for compatibility with search service."""
        return self.business_evaluation_tier

    # Timestamps (from companies - may be nullable for migrated data)
    created_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    
        # Relationships
    claimed_by_user: Mapped[Optional["User"]] = relationship(
        "User", back_populates="claimed_providers"
    )
    memberships: Mapped[List["ProviderMembership"]] = relationship(
        "ProviderMembership", back_populates="provider", cascade="all, delete-orphan"
    )
    claim_requests: Mapped[List["ProviderClaimRequest"]] = relationship(
        "ProviderClaimRequest", back_populates="provider", cascade="all, delete-orphan"
    )
    rfq_matches: Mapped[List["RFQMatch"]] = relationship(
        "RFQMatch", back_populates="provider"
    )
    rfq_dispatches: Mapped[List["RFQDispatch"]] = relationship(
        "RFQDispatch", back_populates="provider"
    )
    rfq_unlocks: Mapped[List["RFQUnlock"]] = relationship(
        "RFQUnlock", back_populates="provider"
    )
    quotes: Mapped[List["Quote"]] = relationship(
        "Quote", back_populates="provider"
    )
    nda_signatures: Mapped[List["RFQNDA"]] = relationship(
        "RFQNDA", back_populates="provider"
    )
    subscriptions: Mapped[List["Subscription"]] = relationship(
        "Subscription", back_populates="provider"
    )
    advertisements: Mapped[List["Advertisement"]] = relationship(
        "Advertisement", back_populates="provider"
    )
    tier_evaluation_requests: Mapped[List["TierEvaluationRequest"]] = relationship(
        "TierEvaluationRequest", back_populates="provider"
    )

class ProviderMembership(Base):
    """Maps users to providers with specific roles."""
    
    __tablename__ = "provider_memberships"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    provider_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("providers.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    membership_role: Mapped[MembershipRole] = mapped_column(
        String, nullable=False
    )
    status: Mapped[MembershipStatus] = mapped_column(
        String, nullable=False, default=MembershipStatus.ACTIVE
    )
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    
    # Relationships
    provider: Mapped["Provider"] = relationship("Provider", back_populates="memberships")
    user: Mapped["User"] = relationship("User", back_populates="provider_memberships", foreign_keys="ProviderMembership.user_id")


class ProviderClaimRequest(Base):
    """Provider ownership claim requests pending admin review."""
    
    __tablename__ = "provider_claim_requests"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    provider_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("providers.id", ondelete="CASCADE"), nullable=False
    )
    claimant_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[ClaimStatus] = mapped_column(
        String, nullable=False, default=ClaimStatus.PENDING
    )
    proof_type: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    proof_payload: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON, nullable=True
    )
    submitted_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    admin_review_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    reviewed_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    
    # Relationships
    provider: Mapped["Provider"] = relationship(
        "Provider", back_populates="claim_requests"
    )
    claimant_user: Mapped["User"] = relationship(
        "User", back_populates="claim_requests", foreign_keys="ProviderClaimRequest.claimant_user_id"
    )
    reviewed_by_user: Mapped[Optional["User"]] = relationship(
        "User", foreign_keys="ProviderClaimRequest.reviewed_by"
    )
