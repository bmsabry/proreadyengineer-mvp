"""Email-failure log model.

Persists every email-delivery failure (whether detected at send time or
asynchronously via the Resend webhook) so admins can see them in the
Debugging panel and confirm each one.

One row per failed delivery attempt.
"""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


# Free-form string instead of a real DB enum so adding new sources later
# doesn't need a migration. Values used in code:
#   "sync_api_error"        - Resend HTTP returned non-2xx
#   "sync_smtp_error"       - SMTP transport failed/timed out
#   "sync_no_provider"      - No delivery method configured at all
#   "webhook_bounced"       - Resend email.bounced
#   "webhook_complained"    - Resend email.complained
#   "webhook_delivery_delayed" - Resend email.delivery_delayed
#   "webhook_failed"        - Resend email.failed (generic)
class EmailFailure(Base):
    """One entry per failed email delivery."""

    __tablename__ = "email_failures"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # The recipient address that failed
    to_email: Mapped[str] = mapped_column(String(320), nullable=False, index=True)
    # The subject of the email that failed (best-effort; webhook payloads may not include it)
    subject: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    # Where this failure was detected
    source: Mapped[str] = mapped_column(String(48), nullable=False, index=True)
    # HTTP status code if sync, bounce code if webhook
    error_code: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    # Short error message extracted from the response
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # The raw provider payload (truncated) so admins can see what Resend said
    provider_response: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Resend's email/message id when available (lets us correlate across events)
    resend_email_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)

    # Workflow: starts unresolved; admin clicks Mark Resolved to clear
    resolved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("false"), index=True)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_by_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )
