"""Support ticket models for the semi-automated customer support system."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.enums import (
    SupportTicketCategory,
    SupportTicketPriority,
    SupportTicketStatus,
)

if TYPE_CHECKING:
    from app.models.user import User


class SupportTicket(Base):
    """Support ticket — one thread per customer issue.

    Tracks the full lifecycle from first contact through resolution.
    Can be created from:
    - Public contact form (no auth)
    - Authenticated portal contact form
    - Inbound email via Resend inbound webhook
    """

    __tablename__ = "support_tickets"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # -----------------------------------------------------------------------
    # Submitter identity (nullable — anonymous submissions allowed)
    # -----------------------------------------------------------------------
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # Always captured — either from form or email From header
    submitter_email: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    submitter_name: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # -----------------------------------------------------------------------
    # Ticket content
    # -----------------------------------------------------------------------
    subject: Mapped[str] = mapped_column(Text, nullable=False)
    # Original message body stored here; subsequent messages in ticket_messages
    body: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # -----------------------------------------------------------------------
    # Classification (populated by LLM or admin override)
    # -----------------------------------------------------------------------
    category: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
        default=SupportTicketCategory.GENERAL.value,
    )
    priority: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        default=SupportTicketPriority.P5_GENERAL.value,
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default=SupportTicketStatus.NEW.value,
        index=True,
    )

    # -----------------------------------------------------------------------
    # Email threading — used to match inbound replies to existing tickets
    # -----------------------------------------------------------------------
    # The Message-ID header of the first outbound email sent for this ticket
    email_message_id: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, index=True
    )
    # Raw In-Reply-To / References headers from inbound webhook
    inbound_in_reply_to: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # -----------------------------------------------------------------------
    # Source tracking
    # -----------------------------------------------------------------------
    # "contact_form" | "contact_form_auth" | "inbound_email"
    source: Mapped[str] = mapped_column(
        String(64), nullable=False, default="contact_form"
    )

    # -----------------------------------------------------------------------
    # Assignment & LLM state
    # -----------------------------------------------------------------------
    assigned_to_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # Stores LLM conversation context between turns (list of message dicts)
    llm_session: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON, nullable=True
    )
    # How many times the LLM has attempted auto-resolution for this ticket
    llm_attempt_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )

    # -----------------------------------------------------------------------
    # Spam / abuse flags
    # -----------------------------------------------------------------------
    is_spam: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )

    # -----------------------------------------------------------------------
    # Timestamps
    # -----------------------------------------------------------------------
    first_responded_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    resolved_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_customer_message_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # -----------------------------------------------------------------------
    # Flexible metadata (IP address, user-agent, referrer, etc.)
    # -----------------------------------------------------------------------
    metadata_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON, nullable=True
    )

    # -----------------------------------------------------------------------
    # Relationships
    # -----------------------------------------------------------------------
    user: Mapped[Optional["User"]] = relationship(
        "User",
        foreign_keys=[user_id],
        backref="support_tickets",
    )
    assigned_to: Mapped[Optional["User"]] = relationship(
        "User",
        foreign_keys=[assigned_to_user_id],
    )
    messages: Mapped[List["SupportTicketMessage"]] = relationship(
        "SupportTicketMessage",
        back_populates="ticket",
        cascade="all, delete-orphan",
        order_by="SupportTicketMessage.created_at",
    )
    events: Mapped[List["SupportTicketEvent"]] = relationship(
        "SupportTicketEvent",
        back_populates="ticket",
        cascade="all, delete-orphan",
        order_by="SupportTicketEvent.created_at",
    )


class SupportTicketMessage(Base):
    """Individual message within a support ticket thread.

    Sender types:
    - "customer"  — message sent by the customer (form, email reply)
    - "admin"     — message sent by a human admin
    - "llm"       — auto-generated response by the LLM
    """

    __tablename__ = "support_ticket_messages"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    ticket_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("support_tickets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # "customer" | "admin" | "llm"
    sender_type: Mapped[str] = mapped_column(String(32), nullable=False)
    sender_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    # Display name shown in thread view
    sender_name: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # -----------------------------------------------------------------------
    # Message content
    # -----------------------------------------------------------------------
    body_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    body_html: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # -----------------------------------------------------------------------
    # Email envelope data (populated for inbound/outbound email messages)
    # -----------------------------------------------------------------------
    # The RFC 2822 Message-ID of this specific email message
    email_message_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Direction: "inbound" | "outbound" | "form" (web form submission)
    direction: Mapped[str] = mapped_column(
        String(16), nullable=False, default="form"
    )
    # Whether the outbound email was successfully delivered
    email_delivered: Mapped[Optional[bool]] = mapped_column(
        Boolean, nullable=True
    )

    # -----------------------------------------------------------------------
    # Relationships
    # -----------------------------------------------------------------------
    ticket: Mapped["SupportTicket"] = relationship(
        "SupportTicket", back_populates="messages"
    )
    sender_user: Mapped[Optional["User"]] = relationship(
        "User", foreign_keys=[sender_user_id]
    )


class SupportTicketEvent(Base):
    """Immutable audit trail event for a support ticket.

    Records every status change, assignment, escalation, and LLM action.
    """

    __tablename__ = "support_ticket_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    ticket_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("support_tickets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Event types:
    # status_change | assigned | escalated | llm_response | admin_reply
    # customer_reply | auto_resolved | spam_flagged | priority_change
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)

    # The user who triggered the event (null = system / LLM)
    actor_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Flexible payload — stores before/after values, reason text, etc.
    payload: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)

    # -----------------------------------------------------------------------
    # Relationships
    # -----------------------------------------------------------------------
    ticket: Mapped["SupportTicket"] = relationship(
        "SupportTicket", back_populates="events"
    )
    actor: Mapped[Optional["User"]] = relationship(
        "User", foreign_keys=[actor_user_id]
    )
