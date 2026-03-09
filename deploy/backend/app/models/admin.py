"""Admin and audit logging models."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    JSON)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.enums import TierEvaluationStatus

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.provider import Provider


class TierEvaluationRequest(Base):
    """Provider tier upgrade evaluation requests.
    
    Feeds into admin review queue for tier assessment.
    """
    
    __tablename__ = "tier_evaluation_requests"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    provider_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("providers.id"), nullable=False
    )
    requested_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    current_tier: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    requested_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    supporting_payload: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON, nullable=True
    )
    status: Mapped[TierEvaluationStatus] = mapped_column(
        String, nullable=False, default=TierEvaluationStatus.PENDING
    )
    reviewed_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    review_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    new_tier: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Relationships
    provider: Mapped["Provider"] = relationship(
        "Provider", back_populates="tier_evaluation_requests"
    )
    requested_by_user: Mapped["User"] = relationship(
        "User", back_populates="tier_evaluation_requests", foreign_keys="TierEvaluationRequest.requested_by_user_id"
    )
    reviewed_by_user: Mapped[Optional["User"]] = relationship(
        "User", foreign_keys="TierEvaluationRequest.reviewed_by"
    )


class AuditLog(Base):
    """Audit logging for sensitive operations.
    
    Tracks critical actions with before/after state for compliance.
    """
    
    __tablename__ = "audit_logs"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    actor_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    entity_type: Mapped[str] = mapped_column(
        Text, nullable=False
    )  # rfq, provider, user, payment, etc.
    entity_id: Mapped[str] = mapped_column(
        Text, nullable=False
    )  # UUID or string ID
    action: Mapped[str] = mapped_column(
        Text, nullable=False
    )  # created, updated, deleted, status_changed, etc.
    before_state: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON, nullable=True
    )
    after_state: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON, nullable=True
    )
    extra_data: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON, nullable=True
    )
    ip_address: Mapped[Optional[str]] = mapped_column(nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Relationships
    actor_user: Mapped[Optional["User"]] = relationship(
        "User", back_populates="audit_logs"
    )
