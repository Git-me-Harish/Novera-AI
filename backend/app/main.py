"""
Main FastAPI application entry point.
Configures routes, middleware, and application lifecycle events.
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from loguru import logger
import sys

from app.core.config import settings
from app.db.session import init_db, close_db
from app.api.endpoints import health, documents, auth
from app.api.endpoints import chat  # Updated chat with full RAG
from app.api.endpoints import search


# Configure Loguru logger
logger.remove()  # Remove default handler
logger.add(
    sys.stdout,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
    level=settings.log_level,
    colorize=True
)
logger.add(
    settings.log_file,
    format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
    level=settings.log_level,
    rotation=settings.log_rotation,
    retention=settings.log_retention,
    compression="zip"
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager.
    Handles startup and shutdown events.
    """
    # Startup
    logger.info("🚀 Starting Mentanova AI Knowledge Assistant...")
    logger.info(f"Environment: {settings.environment}")
    logger.info(f"Debug mode: {settings.debug}")
    
    try:
        # Initialize database
        await init_db()
        logger.info("✅ Database initialized")
        
        # TODO: Initialize Redis connection
        # await init_redis()
        
        # TODO: Load embedding model
        # await load_embedding_model()
        
        logger.info("🎉 Application startup complete!")
        
    except Exception as e:
        logger.error(f"❌ Startup failed: {str(e)}")
        raise
    
    yield  # Application runs here
    
    # Shutdown
    logger.info("🛑 Shutting down Mentanova AI Knowledge Assistant...")
    
    try:
        await close_db()
        logger.info("✅ Database connections closed")
        
        # TODO: Close Redis connection
        # await close_redis()
        
        logger.info("👋 Shutdown complete")
        
    except Exception as e:
        logger.error(f"❌ Shutdown error: {str(e)}")


# Create FastAPI application
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="AI-powered knowledge assistant with RAG capabilities for finance and HRMS documentation",
    docs_url="/api/docs" if settings.debug else None,
    redoc_url="/api/redoc" if settings.debug else None,
    openapi_url="/api/openapi.json" if settings.debug else None,
    lifespan=lifespan
)


# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=settings.cors_allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"]
)


# Add GZip compression for responses
app.add_middleware(GZipMiddleware, minimum_size=1000)


# Include routers
app.include_router(
    health.router,
    prefix=settings.api_v1_prefix,
    tags=["Health"]
)

app.include_router(
    auth.router,
    prefix=settings.api_v1_prefix,
    tags=["Authentication"]
)

app.include_router(
    documents.router,
    prefix=settings.api_v1_prefix,
    tags=["Documents"]
)

from app.api.endpoints import search
app.include_router(
    search.router,
    prefix=settings.api_v1_prefix,
    tags=["Search"]
)

app.include_router(
    chat.router,
    prefix=settings.api_v1_prefix,
    tags=["Chat"]
)


@app.get("/")
async def root():
    """Root endpoint - API information."""
    return {
        "name": settings.app_name,
        "version": settings.app_version,
        "status": "operational",
        "docs": "/api/docs" if settings.debug else "disabled in production"
    }


# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """Catch all unhandled exceptions."""
    logger.error(f"Unhandled exception: {str(exc)}", exc_info=True)
    return {
        "error": "Internal server error",
        "message": str(exc) if settings.debug else "An error occurred"
    }


if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        workers=1 if settings.debug else settings.workers,
        log_level=settings.log_level.lower()
    )