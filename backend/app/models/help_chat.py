"""Help Assistant chat log model.

Logs every user turn and assistant response for admin review and abuse analysis.
One row per assistant turn.
"""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class HelpChatLog(Base):
    """One entry per AI Help Assistant assistant-turn."""

    __tablename__ = "help_chat_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    user_role: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    user_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    user_message: Mapped[str] = mapped_column(Text, nullable=False, default="")
    assistant_reply: Mapped[str] = mapped_column(Text, nullable=False, default="")
    prompt_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    completion_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    total_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    model: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    latency_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    # Estimated USD cost of this turn (LLM4 + any LLM3 delegation), for per-user
    # monthly budget metering. Nullable for legacy rows.
    cost_usd: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    # User feedback on this assistant turn: 1 = thumbs up, -1 = thumbs down, NULL = none.
    feedback: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
