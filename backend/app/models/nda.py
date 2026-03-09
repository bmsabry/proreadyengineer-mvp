"""NDA document signing and management models."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.enums import NdaStatus

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.provider import Provider
    from app.models.rfq import RFQ


class RFQNDA(Base):
    """NDA document signing and audit trail."""
    
    __tablename__ = "rfq_ndas"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    rfq_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("rfqs.id", ondelete="CASCADE"),
        nullable=False,
    )
    provider_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("providers.id", ondelete="CASCADE"),
        nullable=True,
    )
    customer_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    nda_status: Mapped[NdaStatus] = mapped_column(
        String(50),
        nullable=False,
        default=NdaStatus.NOT_REQUIRED,
    )
    signrequest_document_id: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )
    signrequest_template_id: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )
    signed_pdf_s3_key: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True,
    )
    audit_trail_s3_key: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True,
    )
    customer_signed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    provider_signed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    fully_signed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )
    
    # Relationships
    rfq: Mapped["RFQ"] = relationship("RFQ", back_populates="ndas")
    provider: Mapped[Optional["Provider"]] = relationship("Provider", back_populates="nda_signatures")
    customer_user: Mapped[Optional["User"]] = relationship("User", back_populates="ndas", foreign_keys="RFQNDA.customer_user_id")
