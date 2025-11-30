"""
Health check endpoints for monitoring system status.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from datetime import datetime
from typing import Dict, Any
import asyncio

from app.db.session import get_db
from app.core.config import settings

router = APIRouter()


@router.get("/health", response_model=Dict[str, Any])
async def health_check():
    """
    Basic health check endpoint.
    Returns application status without external dependencies.
    """
    return {
        "status": "healthy",
        "service": settings.app_name,
        "version": settings.app_version,
        "timestamp": datetime.utcnow().isoformat(),
        "environment": settings.environment
    }


@router.get("/health/detailed", response_model=Dict[str, Any])
async def detailed_health_check(db: AsyncSession = Depends(get_db)):
    """
    Detailed health check including database and cache connectivity.
    """
    health_status = {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "checks": {}
    }
    
    # Check database connectivity
    try:
        result = await db.execute(text("SELECT 1"))
        result.fetchone()
        health_status["checks"]["database"] = {
            "status": "healthy",
            "message": "PostgreSQL connection successful"
        }
    except Exception as e:
        health_status["status"] = "unhealthy"
        health_status["checks"]["database"] = {
            "status": "unhealthy",
            "message": f"Database connection failed: {str(e)}"
        }
    
    # Check pgvector extension
    try:
        result = await db.execute(
            text("SELECT EXISTS(SELECT 1 FROM pg_extension WHERE extname = 'vector')")
        )
        has_vector = result.scalar()
        if has_vector:
            health_status["checks"]["pgvector"] = {
                "status": "healthy",
                "message": "pgvector extension available"
            }
        else:
            health_status["checks"]["pgvector"] = {
                "status": "warning",
                "message": "pgvector extension not installed"
            }
    except Exception as e:
        health_status["checks"]["pgvector"] = {
            "status": "unhealthy",
            "message": f"pgvector check failed: {str(e)}"
        }
    
    # TODO: Add Redis health check
    # try:
    #     await redis_client.ping()
    #     health_status["checks"]["cache"] = {
    #         "status": "healthy",
    #         "message": "Redis connection successful"
    #     }
    # except Exception as e:
    #     health_status["checks"]["cache"] = {
    #         "status": "unhealthy",
    #         "message": f"Redis connection failed: {str(e)}"
    #     }
    
    # Check OpenAI API key (without making API call)
    if settings.openai_api_key and not settings.openai_api_key.startswith("your-"):
        health_status["checks"]["openai_config"] = {
            "status": "healthy",
            "message": "OpenAI API key configured"
        }
    else:
        health_status["checks"]["openai_config"] = {
            "status": "warning",
            "message": "OpenAI API key not properly configured"
        }
    
    # Overall status determination
    unhealthy_checks = [
        check for check in health_status["checks"].values()
        if check["status"] == "unhealthy"
    ]
    
    if unhealthy_checks:
        health_status["status"] = "unhealthy"
    
    return health_status


@router.get("/health/ready", response_model=Dict[str, str])
async def readiness_check(db: AsyncSession = Depends(get_db)):
    """
    Kubernetes-style readiness probe.
    Returns 200 if service is ready to accept traffic.
    """
    try:
        # Check database
        await db.execute(text("SELECT 1"))
        
        # TODO: Check Redis
        # await redis_client.ping()
        
        return {"status": "ready"}
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=f"Service not ready: {str(e)}"
        )


@router.get("/health/live", response_model=Dict[str, str])
async def liveness_check():
    """
    Kubernetes-style liveness probe.
    Returns 200 if service is alive (doesn't check dependencies).
    """
    return {"status": "alive"}