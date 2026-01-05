"""
Main FastAPI application entry point.
Configures routes, middleware, and application lifecycle events.
"""

from contextlib import asynccontextmanager
from pathlib import Path
import sys

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from loguru import logger

from app.core.config import settings
from app.db.session import init_db, close_db
from app.api.endpoints import (
    health,
    documents,
    auth,
    chat,
    search,
    admin,
    document_editor,
    customization,
)

# -------------------------------------------------
# Logging
# -------------------------------------------------
logger.remove()
logger.add(
    sys.stdout,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | "
           "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
           "<level>{message}</level>",
    level=settings.log_level,
    colorize=True,
)

logger.add(
    settings.log_file,
    format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
    level=settings.log_level,
    rotation=settings.log_rotation,
    retention=settings.log_retention,
    compression="zip",
)

# -------------------------------------------------
# Lifespan
# -------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 Starting Novera AI Knowledge Assistant")
    logger.info(f"Environment: {settings.environment}")

    try:
        await init_db()
        logger.info("✅ Database initialized")

        Path(settings.upload_dir).mkdir(parents=True, exist_ok=True)
        Path(settings.upload_dir, "branding").mkdir(parents=True, exist_ok=True)
        logger.info("✅ Upload directories ready")

    except Exception:
        logger.exception("❌ Startup failed")
        raise

    yield

    logger.info("🛑 Shutting down application")
    await close_db()
    logger.info("✅ Database closed")


# -------------------------------------------------
# App
# -------------------------------------------------
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    docs_url="/api/docs" if settings.debug else None,
    redoc_url="/api/redoc" if settings.debug else None,
    openapi_url="/api/openapi.json" if settings.debug else None,
    lifespan=lifespan,
)

# -------------------------------------------------
# Middleware
# -------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=settings.cors_allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(GZipMiddleware, minimum_size=1000)

# -------------------------------------------------
# Static: uploads
# -------------------------------------------------
upload_path = Path(settings.upload_dir)
if upload_path.exists():
    app.mount("/uploads", StaticFiles(directory=upload_path), name="uploads")

# -------------------------------------------------
# API Routes (ALL under /api)
# -------------------------------------------------
app.include_router(health.router, prefix=settings.api_v1_prefix, tags=["Health"])
app.include_router(auth.router, prefix=settings.api_v1_prefix, tags=["Auth"])
app.include_router(documents.router, prefix=settings.api_v1_prefix, tags=["Documents"])
app.include_router(search.router, prefix=settings.api_v1_prefix, tags=["Search"])
app.include_router(chat.router, prefix=settings.api_v1_prefix, tags=["Chat"])
app.include_router(customization.router, prefix=settings.api_v1_prefix, tags=["Customization"])
app.include_router(admin.router, prefix=settings.api_v1_prefix, tags=["Admin"])
app.include_router(document_editor.router, prefix=settings.api_v1_prefix, tags=["Editor"])

# -------------------------------------------------
# Frontend SPA (✅ CORRECT WAY)
# -------------------------------------------------
FRONTEND_DIR = Path("/app/backend/static")

if FRONTEND_DIR.exists():
    app.mount(
        "/",
        StaticFiles(directory=FRONTEND_DIR, html=True),
        name="frontend",
    )
    logger.info(f"✅ Frontend mounted at / from {FRONTEND_DIR}")
else:
    logger.warning("⚠️ Frontend build not found")

# -------------------------------------------------
# Exception handling
# -------------------------------------------------
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception(f"Unhandled error on {request.url.path}")
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "message": str(exc) if settings.debug else "Unexpected error",
        },
    )
