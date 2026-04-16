from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean
from datetime import datetime
from app.models.base import Base


class SystemConfig(Base):
    """Runtime key/value configuration store managed via admin UI.

    NOTE: Explicitly overrides Base.created_at and Base.updated_at to be nullable=True
    so they are compatible with the existing DB schema created by migration e1f2g3h4i5j6.
    """
    __tablename__ = 'system_config'

    id = Column(Integer, primary_key=True, autoincrement=True)
    key = Column(String(100), unique=True, nullable=False, index=True)
    value = Column(Text, nullable=True)
    is_secret = Column(Boolean, default=True, nullable=True)

    # Explicitly override Base Mapped columns with nullable=True versions
    # to match the actual DB schema (migration e1f2g3h4i5j6 created them nullable)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=True)  # type: ignore[assignment]
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=True)  # type: ignore[assignment]
    updated_by = Column(String(100), nullable=True)  # user id (UUID stored as string)
