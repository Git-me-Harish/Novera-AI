"""
Database session management with async support.
Configures SQLAlchemy with pgvector extension for vector operations.
"""
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import declarative_base
from sqlalchemy.pool import NullPool
from sqlalchemy import event, text
from loguru import logger

from app.core.config import settings


# Create async engine with optimized connection pooling
engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
    pool_size=settings.database_pool_size,
    max_overflow=settings.database_max_overflow,
    pool_pre_ping=True,  # Verify connections before using
    pool_recycle=3600,   # Recycle connections after 1 hour
)


# Session factory for creating new sessions
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


# Base class for all models
Base = declarative_base()


async def init_db() -> None:
    """
    Initialize database with required extensions and tables.
    Must be called on application startup.
    """
    async with engine.begin() as conn:
        # Enable pgvector extension
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        logger.info("✅ pgvector extension enabled")
        
        # Enable pg_trgm for better text search
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
        logger.info("✅ pg_trgm extension enabled for text search")
        
        # Create all tables
        await conn.run_sync(Base.metadata.create_all)
        logger.info("✅ Database tables created")


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency for getting async database sessions.
    
    Usage in FastAPI endpoints:
        @app.get("/items")
        async def get_items(db: AsyncSession = Depends(get_db)):
            # Use db session here
            pass
    
    Yields:
        AsyncSession: Database session that auto-closes after use
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def close_db() -> None:
    """
    Close database connections.
    Should be called on application shutdown.
    """
    await engine.dispose()
    logger.info("✅ Database connections closed")


# Event listeners for connection lifecycle
@event.listens_for(engine.sync_engine, "connect")
def set_search_path(dbapi_conn, connection_record):
    """Set search path and optimize settings for each connection."""
    cursor = dbapi_conn.cursor()
    cursor.execute("SET search_path TO public")
    cursor.execute("SET timezone TO 'UTC'")
    cursor.close()


__all__ = ["engine", "AsyncSessionLocal", "Base", "get_db", "init_db", "close_db"]