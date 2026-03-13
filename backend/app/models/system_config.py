from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean
from datetime import datetime
from app.models.base import Base


class SystemConfig(Base):
    __tablename__ = 'system_config'

    id = Column(Integer, primary_key=True)
    key = Column(String(100), unique=True, nullable=False, index=True)
    value = Column(Text, nullable=True)
    is_secret = Column(Boolean, default=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    updated_by = Column(String(100), nullable=True)  # user id (UUID stored as string)
