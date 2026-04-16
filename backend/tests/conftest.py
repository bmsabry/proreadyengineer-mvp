"""Pytest configuration and fixtures for ProReadyEngineer backend tests."""

import asyncio
import hashlib
import uuid
from datetime import datetime, timedelta
from typing import AsyncGenerator, Generator, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

# Import app components
import sys
sys.path.insert(0, '/a0/usr/projects/website_for_engineering_directory/backend')

from app.db.session import get_db, async_engine
from main import app as fastapi_app
from app.models.base import Base
from app.services.auth_service import hash_password

# Use SQLite in-memory for tests
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="function")
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Create a fresh database session for each test."""
    # Create tables
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    # Create session
    SessionLocal = sessionmaker(
        async_engine, class_=AsyncSession, expire_on_commit=False
    )
    async with SessionLocal() as session:
        yield session

    # Cleanup
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture(scope="function")
async def async_client(db_session) -> AsyncGenerator[AsyncClient, None]:
    """Create async test client with test database."""

    async def override_get_db():
        yield db_session

    # Override the dependency
    fastapi_app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=fastapi_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    # Reset overrides
    fastapi_app.dependency_overrides.clear()


@pytest.fixture(scope="function")
def client(db_session):
    """Create synchronous test client with test database."""
    async def override_get_db():
        yield db_session

    # Override the dependency
    fastapi_app.dependency_overrides[get_db] = override_get_db

    with TestClient(fastapi_app) as test_client:
        yield test_client

    # Reset overrides
    fastapi_app.dependency_overrides.clear()


@pytest.fixture
def mock_stripe():
    """Mock Stripe API."""
    with patch('app.services.payment_service.stripe') as mock:
        mock.PaymentIntent.create = MagicMock(return_value={
            'id': 'pi_test_123',
            'client_secret': 'secret_test',
            'status': 'requires_action'
        })
        yield mock


@pytest.fixture
def mock_openai():
    """Mock OpenAI API."""
    with patch('app.services.search_service.openai') as mock:
        mock.embeddings.create = MagicMock(return_value=MagicMock(
            data=[MagicMock(embedding=[0.1] * 1536)]
        ))
        mock.chat.completions.create = MagicMock(return_value=MagicMock(
            choices=[MagicMock(message=MagicMock(content='{"requires_engineering": 1}'))]
        ))
        yield mock


@pytest.fixture
def mock_s3():
    """Mock S3 operations."""
    with patch('app.services.file_service.boto3') as mock:
        mock.client = MagicMock(return_value=MagicMock(
            generate_presigned_url=MagicMock(return_value='https://s3.presigned.url'),
            put_object=MagicMock(return_value={})
        ))
        yield mock



@pytest.fixture
async def customer_user(db_session):
    """Create a test customer user."""
    from app.models.user import User

    user = User(
        email="customer@test.com",
        password_hash=hash_password("password123"),
        first_name="Test",
        last_name="Customer",
        roles=["customer"],
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user
