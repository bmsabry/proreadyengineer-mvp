"""Database base model re-export.

This module re-exports the SQLAlchemy Base from models.base
for use in database-related imports (alembic, etc.).
"""

from app.models.base import Base

__all__ = ["Base"]
