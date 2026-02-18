"""
Main FastAPI application entry point.
Configures routes, middleware, and application lifecycle events.
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from loguru import logger
import sys
from pathlib import Path
from app.api.endpoints import organization
from app.core.config import settings
from app.db.session import init_db, close_db
from app.api.endpoints import health, documents, auth, chat, search, admin, document_editor, customization


# Configure Loguru logger
logger.remove()
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
    logger.info("🚀 Starting Novera AI Knowledge Assistant...")
    logger.info(f"Environment: {settings.environment}")
    logger.info(f"Debug mode: {settings.debug}")
    logger.info(f"CORS Origins: {settings.cors_origins_list}")
    
    try:
        # Initialize database
        await init_db()
        logger.info("✅ Database initialized")
        
        # Create upload directories
        Path(settings.upload_dir).mkdir(parents=True, exist_ok=True)
        Path(settings.upload_dir + "/branding").mkdir(parents=True, exist_ok=True)
        logger.info("✅ Upload directories created")
        
        logger.info("📦 Pre-loading embedding model...")
        try:
            from app.services.embedding.embedding_service import embedding_service
            
            # Force local model initialization
            embedding_service.use_local_fallback = True
            embedding_service._init_local_model()
            
            logger.info("✅ Embedding model pre-loaded")
        except Exception as e:
            logger.warning(f"⚠️ Model pre-load failed: {e}")
        
        logger.info("🎉 Application startup complete!")
        
    except Exception as e:
        logger.error(f"❌ Startup failed: {str(e)}")
        raise
    
    yield  # Application runs here
    
    # Shutdown
    logger.info("🛑 Shutting down Novera AI Knowledge Assistant...")
    
    try:
        await close_db()
        logger.info("✅ Database connections closed")
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


# Configure CORS - USING PROPERTY FOR DOCKER COMPATIBILITY
logger.info(f"🔐 Configuring CORS with origins: {settings.cors_origins_list}")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=settings.cors_allow_credentials,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["*"],
    max_age=3600,
)

logger.info("✅ CORS middleware configured successfully")


# Add GZip compression
app.add_middleware(GZipMiddleware, minimum_size=1000)

# Mount static files for uploads
upload_path = Path(settings.upload_dir)
if upload_path.exists():
    app.mount("/uploads", StaticFiles(directory=str(upload_path)), name="uploads")
    logger.info(f"✅ Static files mounted at /uploads -> {upload_path}")


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

app.include_router(
    customization.router,
    prefix=settings.api_v1_prefix,
    tags=["Customization"]
)

app.include_router(
    organization.router,
    prefix=settings.api_v1_prefix,
    tags=["Super Admin - Organizations"]
)

# Admin routes - requires admin role
app.include_router(
    admin.router,
    prefix=settings.api_v1_prefix,
    tags=["Admin"]
)

app.include_router(
    document_editor.router,
    prefix=settings.api_v1_prefix,
    tags=["Document Editor"]
)


@app.get("/")
async def root():
    """Root endpoint - API information."""
    return {
        "name": settings.app_name,
        "version": settings.app_version,
        "status": "operational",
        "docs": "/api/docs" if settings.debug else "disabled in production",
        "cors_enabled": True,
        "allowed_origins": settings.cors_origins_list if settings.debug else "configured"
    }


# Add OPTIONS handler for preflight requests
@app.options("/{path:path}")
async def options_handler(path: str):
    """Handle preflight OPTIONS requests."""
    return JSONResponse(
        content={"message": "OK"},
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, PATCH, OPTIONS",
            "Access-Control-Allow-Headers": "*",
        }
    )


# Global exception handler - FIXED
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Catch all unhandled exceptions and return proper JSON response."""
    
    # Log the full error with traceback
    logger.error(f"Unhandled exception on {request.method} {request.url.path}")
    logger.error(f"Exception type: {type(exc).__name__}")
    logger.error(f"Exception message: {str(exc)}")
    logger.exception("Full traceback:", exc_info=exc)
    
    # Determine status code
    status_code = 500
    
    # Build error response
    error_detail = {
        "error": "Internal server error",
        "message": str(exc) if settings.debug else "An unexpected error occurred",
        "type": type(exc).__name__ if settings.debug else None,
        "path": str(request.url.path)
    }
    
    # Return JSONResponse instead of dict
    return JSONResponse(
        status_code=status_code,
        content=error_detail
    )


# Add specific exception handlers for common errors
from sqlalchemy.exc import SQLAlchemyError, IntegrityError
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

@app.exception_handler(SQLAlchemyError)
async def sqlalchemy_exception_handler(request: Request, exc: SQLAlchemyError):
    """Handle SQLAlchemy database errors."""
    logger.error(f"Database error on {request.method} {request.url.path}: {str(exc)}")
    logger.exception("Database error details:", exc_info=exc)
    
    return JSONResponse(
        status_code=500,
        content={
            "error": "Database error",
            "message": "A database error occurred" if not settings.debug else str(exc),
            "type": "DatabaseError"
        }
    )


@app.exception_handler(IntegrityError)
async def integrity_exception_handler(request: Request, exc: IntegrityError):
    """Handle database integrity errors (unique constraints, etc)."""
    logger.error(f"Integrity error on {request.method} {request.url.path}: {str(exc)}")
    
    # Parse common integrity errors
    error_msg = str(exc.orig) if hasattr(exc, 'orig') else str(exc)
    
    if "duplicate key" in error_msg.lower() or "unique constraint" in error_msg.lower():
        return JSONResponse(
            status_code=409,
            content={
                "error": "Conflict",
                "message": "A record with this information already exists",
                "type": "IntegrityError"
            }
        )
    
    return JSONResponse(
        status_code=400,
        content={
            "error": "Invalid data",
            "message": "The provided data violates database constraints",
            "type": "IntegrityError"
        }
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle request validation errors."""
    logger.error(f"Validation error on {request.method} {request.url.path}: {exc.errors()}")
    
    return JSONResponse(
        status_code=422,
        content={
            "error": "Validation error",
            "message": "Invalid request data",
            "details": exc.errors() if settings.debug else None
        }
    )


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    """Handle HTTP exceptions."""
    logger.warning(f"HTTP {exc.status_code} on {request.method} {request.url.path}: {exc.detail}")
    
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.detail,
            "message": exc.detail,
            "status_code": exc.status_code
        }
    )


if __name__ == "__main__":
    import uvicorn
    
    logger.info(f"🚀 Starting server on {settings.host}:{settings.port}")
    
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        workers=1 if settings.debug else settings.workers,
        log_level=settings.log_level.lower()
    )
