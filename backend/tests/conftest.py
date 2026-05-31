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

# --- Test-harness portability: render Postgres-only DDL on SQLite ----------------
# Production runs Postgres (pgvector + server_default text("NOW()") etc.). For the
# SQLite-backed unit tests we translate those so Base.metadata.create_all() works.
from sqlalchemy.ext.compiler import compiles as _compiles
from sqlalchemy.sql.elements import TextClause as _TextClause
try:
    from pgvector.sqlalchemy import Vector as _Vector

    @_compiles(_Vector, "sqlite")
    def _render_vector_sqlite(element, compiler, **kw):  # noqa: ANN001
        return "BLOB"
except Exception:  # pragma: no cover
    pass

@_compiles(_TextClause, "sqlite")
def _render_text_sqlite(element, compiler, **kw):  # noqa: ANN001
    t = element.text.strip().lower()
    return {"now()": "CURRENT_TIMESTAMP", "false": "0", "true": "1"}.get(t, element.text)



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


# ---------------------------------------------------------------------------
# CI hang guard: pytest occasionally finishes the test session but the process
# does not return because a non-daemon thread or an unclosed async engine keeps
# the interpreter alive — which left GitHub Actions jobs "in progress" for ~an
# hour after "N passed" was already printed. Once the session is done and the
# exit status is known, flush output and hard-exit so the CI step returns
# immediately. (Safe: this runs only after all tests + reporting are complete.)
# ---------------------------------------------------------------------------
def pytest_sessionfinish(session, exitstatus):  # noqa: D401
    import os as _os
    import sys as _sys
    try:
        _sys.stdout.flush()
        _sys.stderr.flush()
    except Exception:
        pass
    _os._exit(int(exitstatus))
