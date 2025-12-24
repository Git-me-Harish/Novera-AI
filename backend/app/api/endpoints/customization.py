"""
Customization API endpoints for organization branding.
Admin endpoints for managing customization, public endpoint for retrieving.
"""
from typing import Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel, Field, validator
from datetime import datetime
from loguru import logger
import os
import shutil
from pathlib import Path
import re

from app.db.session import get_db
from app.models.user import User
from app.models.customization import OrganizationCustomization
from app.api.dependencies.auth import get_current_admin_user, get_optional_user
from app.core.config import settings

router = APIRouter()


# Pydantic Models
class ColorValidator:
    """Validator for hex color codes."""
    @classmethod
    def validate_hex_color(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        if not re.match(r'^#[0-9A-Fa-f]{6}$', value):
            raise ValueError(f'Invalid hex color: {value}. Must be in format #RRGGBB')
        return value.lower()


class CustomizationUpdate(BaseModel):
    """Request model for updating customization."""
    organization_name: Optional[str] = Field(None, min_length=2, max_length=255)
    
    # Colors
    primary_color: Optional[str] = None
    secondary_color: Optional[str] = None
    accent_color: Optional[str] = None
    background_color: Optional[str] = None
    sidebar_color: Optional[str] = None
    text_primary_color: Optional[str] = None
    text_secondary_color: Optional[str] = None
    button_primary_color: Optional[str] = None
    button_text_color: Optional[str] = None
    
    # Branding
    app_name: Optional[str] = Field(None, max_length=255)
    app_tagline: Optional[str] = Field(None, max_length=512)
    
    # Custom settings
    custom_settings: Optional[dict] = None
    
    # Validators for all color fields
    @validator('primary_color', 'secondary_color', 'accent_color', 'background_color',
               'sidebar_color', 'text_primary_color', 'text_secondary_color',
               'button_primary_color', 'button_text_color')
    def validate_color(cls, v):
        return ColorValidator.validate_hex_color(v)


class CustomizationResponse(BaseModel):
    """Response model for customization data."""
    id: str
    organization_name: str
    logo_url: Optional[str]
    logo_dark_url: Optional[str]
    favicon_url: Optional[str]
    colors: dict
    branding: dict
    custom_settings: dict
    is_active: bool
    created_at: str
    updated_at: str


# File upload configuration
UPLOAD_DIR = Path(settings.upload_dir) / "branding"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

ALLOWED_IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.svg', '.ico'}
MAX_IMAGE_SIZE_MB = 5


def validate_image_file(file: UploadFile) -> None:
    """Validate uploaded image file."""
    # Check extension
    file_ext = Path(file.filename).suffix.lower()
    if file_ext not in ALLOWED_IMAGE_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid file type. Allowed: {', '.join(ALLOWED_IMAGE_EXTENSIONS)}"
        )
    
    # Check file size (read first chunk to estimate)
    file.file.seek(0, 2)  # Seek to end
    file_size = file.file.tell()
    file.file.seek(0)  # Reset to beginning
    
    max_size_bytes = MAX_IMAGE_SIZE_MB * 1024 * 1024
    if file_size > max_size_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File too large. Maximum size: {MAX_IMAGE_SIZE_MB}MB"
        )


async def save_uploaded_file(file: UploadFile, organization_name: str, file_type: str) -> str:
    """Save uploaded file and return the URL path."""
    validate_image_file(file)
    
    # Generate unique filename
    file_ext = Path(file.filename).suffix.lower()
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    filename = f"{organization_name}_{file_type}_{timestamp}{file_ext}"
    file_path = UPLOAD_DIR / filename
    
    # Save file
    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        logger.error(f"Failed to save file: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save file"
        )
    
    # Return URL path with /uploads prefix (not /api/v1/uploads)
    # This will be served by FastAPI's StaticFiles mount
    return f"/uploads/branding/{filename}"


async def get_or_create_customization(
    db: AsyncSession,
    organization_name: str = "default"
) -> OrganizationCustomization:
    """Get existing customization or create default one."""
    result = await db.execute(
        select(OrganizationCustomization).where(
            OrganizationCustomization.organization_name == organization_name
        )
    )
    customization = result.scalar_one_or_none()
    
    if not customization:
        # Create default customization
        customization = OrganizationCustomization(
            organization_name=organization_name,
            primary_color="#0ea5e9",
            secondary_color="#d946ef",
            accent_color="#8b5cf6",
            background_color="#ffffff",
            sidebar_color="#ffffff",
            text_primary_color="#111827",
            text_secondary_color="#6b7280",
            button_text_color="#ffffff",
            custom_settings={}
        )
        db.add(customization)
        await db.commit()
        await db.refresh(customization)
    
    return customization


# ============================================================================
# ADMIN ENDPOINTS - Manage Customization
# ============================================================================

@router.get("/admin/customization", response_model=CustomizationResponse)
async def get_admin_customization(
    organization_name: str = "default",
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin_user)
):
    """
    Get customization settings for an organization.
    Admin only.
    """
    customization = await get_or_create_customization(db, organization_name)
    return customization.to_dict()


@router.put("/admin/customization", response_model=CustomizationResponse)
async def update_customization(
    request: CustomizationUpdate,
    organization_name: str = "default",
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin_user)
):
    """
    Update customization settings.
    Admin only.
    """
    customization = await get_or_create_customization(db, organization_name)
    
    # Update fields
    update_data = request.dict(exclude_unset=True)
    
    for field, value in update_data.items():
        if hasattr(customization, field) and value is not None:
            setattr(customization, field, value)
    
    customization.updated_at = datetime.utcnow()
    
    await db.commit()
    await db.refresh(customization)
    
    logger.info(f"Admin {admin.email} updated customization for {organization_name}")
    
    return customization.to_dict()


@router.post("/admin/customization/logo")
async def upload_logo(
    file: UploadFile = File(...),
    organization_name: str = "default",
    logo_type: str = "light",  # light, dark, or favicon
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin_user)
):
    """
    Upload organization logo.
    Admin only.
    
    Args:
        file: Image file (PNG, JPG, SVG, ICO)
        organization_name: Organization identifier
        logo_type: Type of logo (light, dark, favicon)
    """
    if logo_type not in ['light', 'dark', 'favicon']:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid logo_type. Must be 'light', 'dark', or 'favicon'"
        )
    
    # Save file
    file_url = await save_uploaded_file(file, organization_name, logo_type)
    
    # Update customization
    customization = await get_or_create_customization(db, organization_name)
    
    if logo_type == "light":
        customization.logo_url = file_url
    elif logo_type == "dark":
        customization.logo_dark_url = file_url
    elif logo_type == "favicon":
        customization.favicon_url = file_url
    
    customization.updated_at = datetime.utcnow()
    
    await db.commit()
    await db.refresh(customization)
    
    logger.info(f"Admin {admin.email} uploaded {logo_type} logo for {organization_name}")
    
    return {
        "message": f"{logo_type.capitalize()} logo uploaded successfully",
        "url": file_url,
        "customization": customization.to_dict()
    }


@router.delete("/admin/customization/logo")
async def delete_logo(
    logo_type: str = "light",
    organization_name: str = "default",
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin_user)
):
    """
    Delete organization logo.
    Admin only.
    """
    if logo_type not in ['light', 'dark', 'favicon']:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid logo_type"
        )
    
    customization = await get_or_create_customization(db, organization_name)
    
    # Get current logo path
    logo_url = None
    if logo_type == "light":
        logo_url = customization.logo_url
        customization.logo_url = None
    elif logo_type == "dark":
        logo_url = customization.logo_dark_url
        customization.logo_dark_url = None
    elif logo_type == "favicon":
        logo_url = customization.favicon_url
        customization.favicon_url = None
    
    # Delete file if exists
    if logo_url:
        file_path = UPLOAD_DIR / Path(logo_url).name
        if file_path.exists():
            try:
                file_path.unlink()
            except Exception as e:
                logger.error(f"Failed to delete file: {str(e)}")
    
    customization.updated_at = datetime.utcnow()
    await db.commit()
    
    logger.info(f"Admin {admin.email} deleted {logo_type} logo for {organization_name}")
    
    return {
        "message": f"{logo_type.capitalize()} logo deleted successfully"
    }


@router.post("/admin/customization/reset")
async def reset_customization(
    organization_name: str = "default",
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin_user)
):
    """
    Reset customization to default values.
    Admin only.
    """
    customization = await get_or_create_customization(db, organization_name)
    
    # Reset to defaults
    customization.logo_url = None
    customization.logo_dark_url = None
    customization.favicon_url = None
    customization.primary_color = "#0ea5e9"
    customization.secondary_color = "#d946ef"
    customization.accent_color = "#8b5cf6"
    customization.background_color = "#ffffff"
    customization.sidebar_color = "#ffffff"
    customization.text_primary_color = "#111827"
    customization.text_secondary_color = "#6b7280"
    customization.button_primary_color = None
    customization.button_text_color = "#ffffff"
    customization.app_name = None
    customization.app_tagline = None
    customization.custom_settings = {}
    customization.updated_at = datetime.utcnow()
    
    await db.commit()
    await db.refresh(customization)
    
    logger.info(f"Admin {admin.email} reset customization for {organization_name}")
    
    return {
        "message": "Customization reset to defaults",
        "customization": customization.to_dict()
    }


# ============================================================================
# PUBLIC ENDPOINT - Get Current User's Customization
# ============================================================================

@router.get("/customization/current", response_model=CustomizationResponse)
async def get_current_customization(
    db: AsyncSession = Depends(get_db),
    user: Optional[User] = Depends(get_optional_user)
):
    """
    Get customization settings for the current user's organization.
    Public endpoint - works with or without authentication.
    
    If user is authenticated, returns their organization's customization.
    If not authenticated, returns default customization.
    """
    organization_name = "default"
    
    if user and user.organization_name:
        organization_name = user.organization_name
    
    customization = await get_or_create_customization(db, organization_name)
    
    return customization.to_dict()


__all__ = ['router']