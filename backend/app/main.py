"""
Main FastAPI application entry point.
Configures routes, middleware, and application lifecycle events.
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, FileResponse
from loguru import logger
import sys
from pathlib import Path

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
logger.add(sys.stdout, level=settings.log_level)

# -------------------------------------------------
# Lifespan
# -------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 Starting Novera AI Knowledge Assistant")
    await init_db()
    Path(settings.upload_dir).mkdir(parents=True, exist_ok=True)
    yield
    await close_db()

# -------------------------------------------------
# App
# -------------------------------------------------
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    docs_url="/api/docs" if settings.debug else None,
    lifespan=lifespan,
)

# -------------------------------------------------
# Middleware
# -------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(GZipMiddleware, minimum_size=1000)

# -------------------------------------------------
# Static paths
# -------------------------------------------------
FRONTEND_DIR = Path("/app/backend/static")
ASSETS_DIR = FRONTEND_DIR / "assets"

# Serve Vite assets
if ASSETS_DIR.exists():
    app.mount("/assets", StaticFiles(directory=ASSETS_DIR), name="assets")

# Serve other static files (favicon, images)
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

# Uploads
upload_path = Path(settings.upload_dir)
if upload_path.exists():
    app.mount("/uploads", StaticFiles(directory=upload_path), name="uploads")

# -------------------------------------------------
# API routes
# -------------------------------------------------
API_PREFIX = settings.api_v1_prefix

app.include_router(health.router, prefix=API_PREFIX)
app.include_router(auth.router, prefix=API_PREFIX)
app.include_router(documents.router, prefix=API_PREFIX)
app.include_router(search.router, prefix=API_PREFIX)
app.include_router(chat.router, prefix=API_PREFIX)
app.include_router(customization.router, prefix=API_PREFIX)
app.include_router(admin.router, prefix=API_PREFIX)
app.include_router(document_editor.router, prefix=API_PREFIX)

# -------------------------------------------------
# SPA fallback (SAFE)
# -------------------------------------------------
@app.get("/{path:path}")
async def spa_fallback(path: str):
    """
    Serve index.html for SPA routes only
    """
    if (
        path.startswith("api")
        or path.startswith("assets")
        or path.startswith("static")
        or path.startswith("uploads")
    ):
        return JSONResponse(status_code=404, content={"detail": "Not found"})

    index_file = FRONTEND_DIR / "index.html"
    return FileResponse(index_file)

# -------------------------------------------------
# Global error handler
# -------------------------------------------------
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled error")
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error"},
    )
