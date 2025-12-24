"""
Organization customization model for white-labeling support.
"""
from datetime import datetime
from uuid import UUID, uuid4
from sqlalchemy import Column, String, Boolean, DateTime, Index
from sqlalchemy.dialects.postgresql import UUID as PGUUID, JSONB

from app.db.session import Base


class OrganizationCustomization(Base):
    """
    Organization customization settings for white-labeling.
    Supports logo, colors, typography, layout, and additional branding configurations.
    """
    __tablename__ = "organization_customizations"

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    
    # Organization identifier (unique per organization)
    organization_name = Column(String(255), unique=True, nullable=False, index=True)
    
    # Logo
    logo_url = Column(String(512), nullable=True)
    logo_dark_url = Column(String(512), nullable=True)
    favicon_url = Column(String(512), nullable=True)
    
    # Primary Colors
    primary_color = Column(String(7), nullable=False, default="#0ea5e9")
    secondary_color = Column(String(7), nullable=False, default="#d946ef")
    accent_color = Column(String(7), nullable=False, default="#8b5cf6")
    
    # Background Colors
    background_color = Column(String(7), nullable=False, default="#ffffff")
    sidebar_color = Column(String(7), nullable=False, default="#ffffff")
    
    # Text Colors
    text_primary_color = Column(String(7), nullable=False, default="#111827")
    text_secondary_color = Column(String(7), nullable=False, default="#6b7280")
    
    # Button Colors
    button_primary_color = Column(String(7), nullable=True)
    button_text_color = Column(String(7), nullable=False, default="#ffffff")
    
    # Typography
    font_family = Column(String(100), nullable=True)
    font_size_base = Column(String(10), nullable=False, default="14px")
    font_size_heading = Column(String(10), nullable=False, default="24px")
    
    # Layout
    border_radius = Column(String(10), nullable=False, default="8px")
    spacing_unit = Column(String(10), nullable=False, default="16px")
    
    # Additional customization settings stored as JSON
    custom_settings = Column(JSONB, nullable=False, default=dict)
    
    # Branding text
    app_name = Column(String(255), nullable=True)
    app_tagline = Column(String(512), nullable=True)
    
    # Feature flags
    is_active = Column(Boolean, default=True, nullable=False)
    
    # Metadata
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = Column(PGUUID(as_uuid=True), nullable=True)
    
    __table_args__ = (
        Index('idx_org_name_active', 'organization_name', 'is_active'),
    )

    def __repr__(self):
        return f"<OrganizationCustomization(org={self.organization_name}, active={self.is_active})>"

    def to_dict(self):
        """Convert to dictionary for API responses."""
        return {
            "id": str(self.id),
            "organization_name": self.organization_name,
            "logo_url": self.logo_url,
            "logo_dark_url": self.logo_dark_url,
            "favicon_url": self.favicon_url,
            "colors": {
                "primary": self.primary_color,
                "secondary": self.secondary_color,
                "accent": self.accent_color,
                "background": self.background_color,
                "sidebar": self.sidebar_color,
                "text_primary": self.text_primary_color,
                "text_secondary": self.text_secondary_color,
                "button_primary": self.button_primary_color or self.primary_color,
                "button_text": self.button_text_color,
            },
            "typography": {
                "font_family": self.font_family,
                "font_size_base": self.font_size_base,
                "font_size_heading": self.font_size_heading,
            },
            "layout": {
                "border_radius": self.border_radius,
                "spacing_unit": self.spacing_unit,
            },
            "branding": {
                "app_name": self.app_name,
                "app_tagline": self.app_tagline,
            },
            "custom_settings": self.custom_settings,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


__all__ = ['OrganizationCustomization']