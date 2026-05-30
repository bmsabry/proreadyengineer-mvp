"""RFQ lifecycle and dispatch management models."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from sqlalchemy import (
    Boolean,
    Computed,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.enums import DispatchStatus, RfqStatus, UnlockStatus

# An RFQ is "closed" purely as a function of its status. is_closed is kept in lockstep
# with rfq_status by the RFQ._sync_is_closed validator (below), so the two can never
# drift. The column is retained (not dropped) because some admin endpoints read/write it
# via raw SQL; the validator makes every ORM status change recompute it.
_CLOSED_RFQ_STATUS_VALUES = frozenset({
    RfqStatus.QUOTE_LIMIT_REACHED.value,
    RfqStatus.CUSTOMER_SELECTED_PROVIDER.value,
    RfqStatus.CLOSED_NO_SELECTION.value,
    RfqStatus.CANCELLED.value,
})

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.provider import Provider
    from app.models.quote import Quote
    from app.models.nda import RFQNDA


class RFQ(Base):
    """Request for Quote - customer project inquiry lifecycle."""
    
    __tablename__ = "rfqs"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    customer_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    customer_email: Mapped[str] = mapped_column(Text, nullable=False)
    business_name: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    contact_name: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    project_description: Mapped[str] = mapped_column(Text, nullable=False)
    urgency: Mapped[Optional[str]] = mapped_column(
        String, nullable=True
    )  # High, Intermediate, Low
    tollgate_phases: Mapped[Optional[List[str]]] = mapped_column(
        JSON, nullable=True
    )  # TG0, TG1, TG3, TG4, TG6, All, Don't Know
    nda_required: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    rfq_status: Mapped[RfqStatus] = mapped_column(
        String, nullable=False, default=RfqStatus.DRAFT
    )
    quote_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    # DATABASE-GENERATED column: always (rfq_status IN <closed statuses>), computed by
    # the DB at write time. NO writable path (ORM/Core/raw all error if they set it),
    # so it can never drift from rfq_status. Close an RFQ by setting rfq_status.
    is_closed: Mapped[bool] = mapped_column(
        Boolean,
        Computed(
            "rfq_status IN ('quote_limit_reached', 'customer_selected_provider', "
            "'closed_no_selection', 'cancelled')",
            persisted=True,
        ),
        nullable=False,
    )
    selected_provider_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("providers.id"), nullable=True
    )
    has_documents: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    submitted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    closed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships
    customer_user: Mapped[Optional["User"]] = relationship(
        "User", back_populates="rfqs", foreign_keys="RFQ.customer_user_id"
    )
    selected_provider: Mapped[Optional["Provider"]] = relationship(
        "Provider"
    )
    files: Mapped[List["RFQFile"]] = relationship(
        "RFQFile", back_populates="rfq", cascade="all, delete-orphan"
    )
    matches: Mapped[List["RFQMatch"]] = relationship(
        "RFQMatch", back_populates="rfq", cascade="all, delete-orphan"
    )
    dispatch_batches: Mapped[List["RFQDispatchBatch"]] = relationship(
        "RFQDispatchBatch", back_populates="rfq", cascade="all, delete-orphan"
    )
    provider_dispatches: Mapped[List["RFQDispatch"]] = relationship(
        "RFQDispatch", back_populates="rfq", cascade="all, delete-orphan"
    )
    unlocks: Mapped[List["RFQUnlock"]] = relationship(
        "RFQUnlock", back_populates="rfq", cascade="all, delete-orphan"
    )
    quotes: Mapped[List["Quote"]] = relationship(
        "Quote", back_populates="rfq", cascade="all, delete-orphan"
    )
    ndas: Mapped[List["RFQNDA"]] = relationship(
        "RFQNDA", back_populates="rfq", cascade="all, delete-orphan"
    )


class RFQFile(Base):
    """RFQ attachment files stored in S3."""
    
    __tablename__ = "rfq_files"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    rfq_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("rfqs.id", ondelete="CASCADE"), nullable=False
    )
    s3_key: Mapped[str] = mapped_column(Text, nullable=False)
    original_filename: Mapped[str] = mapped_column(Text, nullable=False)
    mime_type: Mapped[str] = mapped_column(Text, nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    extracted_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    uploaded_by_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    
    # Relationships
    rfq: Mapped["RFQ"] = relationship("RFQ", back_populates="files")
    uploaded_by_user: Mapped[Optional["User"]] = relationship(
        "User", back_populates="rfq_files"
    )


class RFQMatch(Base):
    """Search ranking snapshot at RFQ creation time."""
    
    __tablename__ = "rfq_matches"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    rfq_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("rfqs.id", ondelete="CASCADE"), nullable=False
    )
    provider_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("providers.id"), nullable=False
    )
    rank_position: Mapped[int] = mapped_column(Integer, nullable=False)
    composite_score: Mapped[int] = mapped_column(Integer, nullable=False)  # 0-100
    specialty_score: Mapped[int] = mapped_column(Integer, nullable=False)  # 0-25
    capabilities_score: Mapped[int] = mapped_column(Integer, nullable=False)  # 0-50
    tier_score: Mapped[int] = mapped_column(Integer, nullable=False)  # 0-25
    scoring_inputs: Mapped[Dict[str, Any]] = mapped_column(
        JSON, nullable=False
    )
    is_dispatched: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    dispatched_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    
    # Relationships
    rfq: Mapped["RFQ"] = relationship("RFQ", back_populates="matches")
    provider: Mapped["Provider"] = relationship("Provider", back_populates="rfq_matches")


class RFQDispatchBatch(Base):
    """Scheduled batches for RFQ dispatch to providers."""
    
    __tablename__ = "rfq_dispatch_batches"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    rfq_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("rfqs.id", ondelete="CASCADE"), nullable=False
    )
    batch_number: Mapped[int] = mapped_column(Integer, nullable=False)
    scheduled_for: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    dispatched_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    status: Mapped[str] = mapped_column(
        Text, nullable=False, default="pending"
    )
    
    # Relationships
    rfq: Mapped["RFQ"] = relationship("RFQ", back_populates="dispatch_batches")
    provider_dispatches: Mapped[List["RFQDispatch"]] = relationship(
        "RFQDispatch", back_populates="batch"
    )


class RFQDispatch(Base):
    """Individual provider dispatch records for RFQ teasers."""
    
    __tablename__ = "rfq_provider_dispatches"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    rfq_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("rfqs.id", ondelete="CASCADE"), nullable=False
    )
    provider_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("providers.id"), nullable=False
    )
    batch_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("rfq_dispatch_batches.id"), nullable=True
    )
    dispatch_status: Mapped[DispatchStatus] = mapped_column(
        String, nullable=False, default=DispatchStatus.PENDING
    )
    teaser_email_sent_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    email_target: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    email_opened_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    teaser_link_clicked_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    
    # Relationships
    rfq: Mapped["RFQ"] = relationship("RFQ", back_populates="provider_dispatches")
    provider: Mapped["Provider"] = relationship(
        "Provider", back_populates="rfq_dispatches"
    )
    batch: Mapped[Optional["RFQDispatchBatch"]] = relationship(
        "RFQDispatchBatch", back_populates="provider_dispatches"
    )


class RFQUnlock(Base):
    """RFQ unlock purchases by providers."""
    
    __tablename__ = "rfq_unlocks"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    rfq_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("rfqs.id", ondelete="CASCADE"), nullable=False
    )
    provider_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("providers.id"), nullable=False
    )
    unlocked_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    payment_attempt_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    unlock_status: Mapped[UnlockStatus] = mapped_column(
        String, nullable=False, default=UnlockStatus.PAYMENT_PENDING
    )
    unlocked_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    
    # Relationships
    rfq: Mapped["RFQ"] = relationship("RFQ", back_populates="unlocks")
    provider: Mapped["Provider"] = relationship(
        "Provider", back_populates="rfq_unlocks"
    )
    unlocked_by_user: Mapped["User"] = relationship(
        "User", back_populates="rfq_unlocks"
    )
