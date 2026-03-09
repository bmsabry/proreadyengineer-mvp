"""Quote submission and lifecycle models."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.enums import QuoteStatus

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.provider import Provider
    from app.models.rfq import RFQ


class Quote(Base):
    """Provider quote submission for an RFQ.
    
    MVP supports one active submitted quote per provider per RFQ.
    """
    
    __tablename__ = "quotes"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    rfq_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("rfqs.id", ondelete="CASCADE"), nullable=False
    )
    provider_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("providers.id"), nullable=False
    )
    submitter_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    quote_status: Mapped[QuoteStatus] = mapped_column(
        String, nullable=False, default=QuoteStatus.DRAFT
    )
    rough_price_min: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(12, 2), nullable=True
    )
    rough_price_max: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(12, 2), nullable=True
    )
    currency: Mapped[str] = mapped_column(
        Text, nullable=False, default="USD", server_default="USD"
    )
    turnaround_estimate_text: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )
    assumptions_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    scope_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    submitted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    customer_viewed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    
    # Relationships
    rfq: Mapped["RFQ"] = relationship("RFQ", back_populates="quotes")
    provider: Mapped["Provider"] = relationship("Provider", back_populates="quotes")
    submitter_user: Mapped["User"] = relationship(
        "User", back_populates="quotes"
    )
    files: Mapped[List["QuoteFile"]] = relationship(
        "QuoteFile", back_populates="quote", cascade="all, delete-orphan"
    )


class QuoteFile(Base):
    """Quote attachment files stored in S3."""
    
    __tablename__ = "quote_files"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    quote_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("quotes.id", ondelete="CASCADE"), nullable=False
    )
    s3_key: Mapped[str] = mapped_column(Text, nullable=False)
    original_filename: Mapped[str] = mapped_column(Text, nullable=False)
    mime_type: Mapped[str] = mapped_column(Text, nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    
    # Relationships
    quote: Mapped["Quote"] = relationship("Quote", back_populates="files")
