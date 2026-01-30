from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    create_async_engine,
    async_sessionmaker,
)
from sqlalchemy.orm import declarative_base
from sqlalchemy import event, text
from loguru import logger

from app.core.config import settings

# ✅ SAFE TO IMPORT (Alembic needs this)
Base = declarative_base()

_engine = None


def get_async_engine():
    """Create async engine lazily (app runtime only)."""
    global _engine

    if _engine is None:
        _engine = create_async_engine(
            settings.database_url,
            echo=settings.debug,
            pool_size=settings.database_pool_size,
            max_overflow=settings.database_max_overflow,
            pool_pre_ping=True,
            pool_recycle=3600,
        )

        @event.listens_for(_engine.sync_engine, "connect")
        def set_search_path(dbapi_conn, connection_record):
            cursor = dbapi_conn.cursor()
            cursor.execute("SET search_path TO public")
            cursor.execute("SET timezone TO 'UTC'")
            cursor.close()

    return _engine


AsyncSessionLocal = async_sessionmaker(
    bind=get_async_engine(),
    class_=AsyncSession,
    expire_on_commit=False,
)


async def init_db() -> None:
    async with get_async_engine().begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
        await conn.run_sync(Base.metadata.create_all)
        logger.info("✅ Database initialized")


async def get_db() -> AsyncGenerator[AsyncSession, None]:
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
    if _engine:
        await _engine.dispose()
        logger.info("✅ Database connections closed")


__all__ = ["Base", "AsyncSessionLocal", "get_db", "init_db", "close_db"]
