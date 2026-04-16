"""Database session management with support for both SQLite and PostgreSQL."""

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from app.core.config import settings

# Determine if we're using SQLite
IS_SQLITE = "sqlite" in settings.DATABASE_URL.lower()

if IS_SQLITE:
    # SQLite async setup (for local development and testing)
    # SQLite doesn't support pool_size or max_overflow
    async_engine = create_async_engine(
        settings.DATABASE_URL,
        echo=False,
        future=True,
    )
else:
    # PostgreSQL async setup (for production)
    async_engine = create_async_engine(
        settings.DATABASE_URL,
        pool_pre_ping=True,
        pool_size=20,
        max_overflow=30,
        echo=False,
        future=True,
    )

AsyncSessionLocal = async_sessionmaker(
    async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def get_db() -> AsyncSession:
    """Dependency for getting database sessions."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def close_db():
    """Close database connections."""
    await async_engine.dispose()
