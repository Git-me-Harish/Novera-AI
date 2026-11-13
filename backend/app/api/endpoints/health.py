""" Health check endpoints for monitoring system status """
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from loguru import logger
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.redis_manager import redis_manager
from app.db.session import get_db
from app.services.document_processing.job_queue import (
    CONSUMER_GROUP,
    DEAD_LETTER_STREAM_KEY,
    METRICS_PREFIX,
    STREAM_KEY,
)

router = APIRouter()


@router.get("/health", response_model=dict[str, Any])
async def health_check():
    """Basic health check — no external dependencies."""
    return {
        "status": "healthy",
        "service": settings.app_name,
        "version": settings.app_version,
        "timestamp": datetime.now(timezone.utc).isoformat(),  # FIX
        "environment": settings.environment,
    }


@router.get("/health/detailed", response_model=dict[str, Any])
async def detailed_health_check(db: AsyncSession = Depends(get_db)):
    """
    Detailed health check including database, pgvector, Redis, and
    API key configuration.
    """
    health: dict[str, Any] = {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),  # FIX
        "checks": {},
    }

    try:
        await db.execute(text("SELECT 1"))
        health["checks"]["database"] = {
            "status": "healthy",
            "message": "PostgreSQL connection successful",
        }
    except Exception as e:
        health["status"] = "unhealthy"
        health["checks"]["database"] = {
            "status": "unhealthy",
            "message": f"Database connection failed: {e}",
        }

    try:
        result = await db.execute(
            text("SELECT EXISTS(SELECT 1 FROM pg_extension WHERE extname = 'vector')")
        )
        has_vector = result.scalar()
        health["checks"]["pgvector"] = {
            "status": "healthy" if has_vector else "warning",
            "message": (
                "pgvector extension available"
                if has_vector
                else "pgvector extension not installed"
            ),
        }
    except Exception as e:
        health["checks"]["pgvector"] = {
            "status": "warning",
            "message": f"pgvector check failed: {e}",
        }

    try:
        await redis_manager.ping()
        health["checks"]["redis"] = {
            "status": "healthy" if redis_manager.is_redis_active else "degraded",
            "message": (
                "Redis connected — cross-worker sessions enabled"
                if redis_manager.is_redis_active
                else "Redis unavailable — using in-memory fallback (single-worker only)"
            ),
        }
        if redis_manager.is_redis_active:
            client = redis_manager._client
            pending = await client.xpending(STREAM_KEY, CONSUMER_GROUP)
            metric_keys = [
                f"{METRICS_PREFIX}{name}"
                for name in ("succeeded", "failed", "retried", "dead_lettered")
            ]
            metric_values = await client.mget(metric_keys)
            health["checks"]["document_queue"] = {
                "status": "healthy",
                "stream_depth": await client.xlen(STREAM_KEY),
                "pending": int((pending or {}).get("pending", 0)),
                "dead_letter_depth": await client.xlen(DEAD_LETTER_STREAM_KEY),
                "metrics": {
                    name: int(value or 0)
                    for name, value in zip(
                        ("succeeded", "failed", "retried", "dead_lettered"),
                        metric_values,
                    )
                },
            }
    except Exception as e:
        health["checks"]["redis"] = {
            "status": "degraded",
            "message": f"Redis check failed: {e}",
        }

    # Configuration only: no provider call, so health checks cost nothing
    # and never leak model names or keys to unauthenticated callers.
    from app.services.ai import registry

    def _configured(spec) -> bool:
        return spec is not None

    health["checks"]["chat_model"] = {
        "status": "healthy" if _configured(registry.platform_chat_spec()) else "warning",
        "message": "configured" if registry.platform_chat_spec() else
        "LLM_PROVIDER/LLM_MODEL not set (tenant models may still be configured)",
    }
    health["checks"]["embedding_model"] = {
        "status": "healthy" if _configured(registry.platform_embedding_spec()) else "unhealthy",
        "message": "configured" if registry.platform_embedding_spec() else
        "EMBEDDING_PROVIDER/EMBEDDING_MODEL not set — retrieval cannot run",
    }
    reranker_off = settings.rerank_provider == "none"
    health["checks"]["rerank_model"] = {
        "status": "healthy" if (registry.platform_rerank_spec() or reranker_off) else "warning",
        "message": "configured" if registry.platform_rerank_spec() else
        ("disabled by configuration" if reranker_off else "not configured — reranking skipped"),
    }

    if any(c["status"] == "unhealthy" for c in health["checks"].values()):
        health["status"] = "unhealthy"
    elif any(c["status"] in ("warning", "degraded") for c in health["checks"].values()):
        health["status"] = "degraded"

    return health


@router.get("/health/ready", response_model=dict[str, str])
async def readiness_check(db: AsyncSession = Depends(get_db)):
    """Kubernetes / Render readiness probe — returns 200 only when the DB is reachable."""
    try:
        await db.execute(text("SELECT 1"))
        return {"status": "ready"}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Service not ready: {e}")


@router.get("/health/live", response_model=dict[str, str])
async def liveness_check():
    """Kubernetes / Render liveness probe — always 200 if process is alive."""
    return {"status": "alive"}


__all__ = ["router"]
