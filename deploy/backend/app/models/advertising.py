"""Advertising engine and ad inventory models."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

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
from app.models.enums import AdStatus

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.provider import Provider
    from app.models.payment import Subscription


class AdSlot(Base):
    """Ad slot inventory for public pages.
    
    Pre-seeded with slots for software-providers and featured-firms pages.
    """
    
    __tablename__ = "ad_slots"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    page_type: Mapped[str] = mapped_column(
        Text, nullable=False
    )  # software-providers, featured-firms
    slot_name: Mapped[str] = mapped_column(Text, nullable=False)
    slot_position: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(
        Text, nullable=False, default="available"
    )
    
    # Relationships
    advertisements: Mapped[List["Advertisement"]] = relationship(
        "Advertisement", back_populates="ad_slot"
    )


class Advertisement(Base):
    """Active advertisements in ad slots."""
    
    __tablename__ = "advertisements"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    ad_slot_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ad_slots.id"), nullable=True
    )
    advertiser_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    provider_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("providers.id"), nullable=True
    )
    stripe_subscription_id: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    promotional_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    outbound_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    image_s3_key: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    optional_price_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    ad_status: Mapped[AdStatus] = mapped_column(
        String, nullable=False, default=AdStatus.EMPTY
    )
    started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    ended_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    
    # Relationships
    ad_slot: Mapped[Optional["AdSlot"]] = relationship(
        "AdSlot", back_populates="advertisements"
    )
    advertiser_user: Mapped["User"] = relationship(
        "User", back_populates="advertisements"
    )
    provider: Mapped[Optional["Provider"]] = relationship(
        "Provider", back_populates="advertisements"
    )
    subscription: Mapped[Optional["Subscription"]] = relationship(
        "Subscription", back_populates="advertisement", uselist=False
    )
