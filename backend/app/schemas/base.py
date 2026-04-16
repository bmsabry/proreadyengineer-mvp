"""Base Pydantic schema configuration."""

from datetime import datetime
from typing import Any, Optional, TypeVar, Generic, List
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class BaseSchemaConfig:
    """Base configuration for all schemas."""

    # Enable ORM mode for SQLAlchemy model serialization
    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        str_strip_whitespace=True,
        use_enum_values=True,
        json_encoders={
            datetime: lambda v: v.isoformat(),
            UUID: str,
        },
    )


class BaseSchema(BaseModel, BaseSchemaConfig):
    """Base schema with common functionality."""

    pass


class IDSchema(BaseSchema):
    """Schema with ID field."""

    id: UUID


class TimestampSchema(BaseSchema):
    """Schema with timestamp fields."""

    created_at: datetime
    updated_at: datetime


class ResponseSchema(IDSchema, TimestampSchema):
    """Standard response schema with ID and timestamps."""

    pass


class PaginationParams(BaseSchema):
    """Pagination query parameters."""

    page: int = 1
    page_size: int = 20

    @property
    def skip(self) -> int:
        """Calculate skip value for SQL queries."""
        return (self.page - 1) * self.page_size

    @property
    def limit(self) -> int:
        """Return limit value for SQL queries."""
        return self.page_size


T = TypeVar("T")


class PaginatedResponse(BaseSchema, Generic[T]):
    """Paginated response wrapper."""

    items: List[T]
    total: int
    page: int
    page_size: int
    pages: int

    @classmethod
    def create(
        cls,
        items: List[T],
        total: int,
        pagination: PaginationParams,
    ) -> "PaginatedResponse[T]":
        """Create paginated response from items and params."""
        pages = (total + pagination.page_size - 1) // pagination.page_size
        return cls(
            items=items,
            total=total,
            page=pagination.page,
            page_size=pagination.page_size,
            pages=max(1, pages),
        )


# Alias for compatibility - PagedResponse must be Generic
PagedResponse = PaginatedResponse


class TokenRefreshRequest(BaseSchema):
    """Request to refresh access token."""
    refresh_token: str
