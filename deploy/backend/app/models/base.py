"""SQLAlchemy base model with pgvector support."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Column, DateTime, event
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from pgvector.sqlalchemy import Vector


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""

    # Generate table names automatically
    def __init_subclass__(cls, **kwargs: Any) -> None:
        if not hasattr(cls, "__tablename__"):
            cls.__tablename__ = cls.__name__.lower()
        super().__init_subclass__(**kwargs)

    # Default columns for all tables
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


def generate_uuid() -> uuid.UUID:
    """Generate a new UUID."""
    return uuid.uuid4()


# Update timestamps on before_flush
@event.listens_for(Base, "before_update", propagate=True)
def update_timestamp(mapper, connection, target):
    """Automatically update updated_at timestamp."""
    target.updated_at = datetime.utcnow()
