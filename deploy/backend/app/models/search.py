"""Search tracking and discovery models."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    JSON,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.user import User


class IPUsageTracking(Base):
    """Track anonymous user search quotas by IP address."""

    __tablename__ = "ip_usage_tracking"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    ip_address: Mapped[str] = mapped_column(String, nullable=False)
    usage_month: Mapped[str] = mapped_column(
        Text, nullable=False
    )  # Format: YYYY-MM
    search_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    # Explicit timestamps — override Base to ensure server_default is set
    # so DB rows inserted without ORM also get timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        server_default=func.now(),
    )

    # Unique constraint on ip_address + usage_month enforced at DB level


class SearchRequest(Base):
    """Log and audit all search requests with LLM extraction results."""

    __tablename__ = "search_requests"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    ip_address: Mapped[Optional[str]] = mapped_column(nullable=True)
    raw_query_text: Mapped[str] = mapped_column(Text, nullable=False)
    extracted_document_text: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )
    normalized_query_text: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )
    llm_structured_output: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON, nullable=True
    )
    embedding_model: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    embedding_version: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    llm_model: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    search_status: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    fallback_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    results_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Relationships
    user: Mapped[Optional["User"]] = relationship("User")
