""" Enhanced user models with authentication support """
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import Column, String, Boolean, DateTime, Index, ForeignKey
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.dialects.postgresql import UUID as PGUUID, JSONB
from sqlalchemy.orm import relationship

from app.db.session import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# Role hierarchy constants — add new roles here once
_ADMIN_ROLES = frozenset({"admin", "org_admin", "super_admin"})
_ORG_ADMIN_ROLES = frozenset({"admin", "org_admin"})


class User(Base):
    """User model with authentication and profile information."""

    __tablename__ = "users"

    # Primary Key
    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)

    # Authentication
    email = Column(String(255), unique=True, nullable=False, index=True)
    username = Column(String(100), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)

    # Profile
    full_name = Column(String(255), nullable=True)
    avatar_url = Column(String(512), nullable=True)

    # Role & Status
    role = Column(String(20), nullable=False, default="user")
    organization_id = Column(
        PGUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    organization = relationship("Organization", back_populates="users")
    is_active = Column(Boolean, default=True, nullable=False)
    is_verified = Column(Boolean, default=False, nullable=False)

    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(
        DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )
    last_login = Column(DateTime(timezone=True), nullable=True)

    # JSONB
    preferences = Column(JSONB, nullable=False, default=dict)
    user_metadata = Column("metadata", JSONB, nullable=False, default=dict)

    __table_args__ = (
        Index("idx_email_active", "email", "is_active"),
        Index("idx_username_active", "username", "is_active"),
    )

    def __repr__(self) -> str:
        return f"<User(id={self.id}, email={self.email}, role={self.role})>"

    # Role helpers:
    def is_admin(self) -> bool:
        return self.role in _ADMIN_ROLES

    def is_super_admin(self) -> bool:
        return self.role == "super_admin"

    def is_org_admin(self) -> bool:
        return self.role in _ORG_ADMIN_ROLES

    # Serialisation:
    def to_dict(
        self,
        include_sensitive: bool = False,
        include_organization: bool = True,
    ) -> dict:
        """
        Convert user to a plain dict.

        Defensive against lazy-load in async contexts: checks SQLAlchemy's
        inspect to see if the organization relationship is already loaded
        before accessing it.
        """
        data: dict = {
            "id": str(self.id),
            "email": self.email,
            "username": self.username,
            "full_name": self.full_name,
            "avatar_url": self.avatar_url,
            "role": self.role,
            "is_active": self.is_active,
            "is_verified": self.is_verified,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "last_login": self.last_login.isoformat() if self.last_login else None,
            "preferences": self.preferences or {},
            "metadata": self.user_metadata or {},
            # FIX: always include, even when None
            "organization_id": str(self.organization_id) if self.organization_id else None,
        }

        if include_organization and self.organization_id:
            insp = sa_inspect(self)
            if "organization" not in insp.unloaded and self.organization:
                data["organization"] = {
                    "id": str(self.organization.id),
                    "name": self.organization.name,
                    "display_name": self.organization.display_name,
                }
            else:
                data["organization"] = None

        return data


class RefreshToken(Base):
    """JWT refresh token — revocable per session."""

    __tablename__ = "refresh_tokens"

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id = Column(PGUUID(as_uuid=True), nullable=False, index=True)
    token = Column(String(512), unique=True, nullable=False, index=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)     # FIX: TIMESTAMPTZ
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    revoked = Column(Boolean, default=False, nullable=False)

    user_agent = Column(String(512), nullable=True)
    ip_address = Column(String(45), nullable=True)

    __table_args__ = (
        Index("idx_token_active", "token", "revoked"),
        Index("idx_user_active", "user_id", "revoked"),
    )

    def __repr__(self) -> str:
        return f"<RefreshToken(id={self.id}, user_id={self.user_id}, revoked={self.revoked})>"


class PasswordResetToken(Base):
    """One-time password reset token."""

    __tablename__ = "password_reset_tokens"

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id = Column(PGUUID(as_uuid=True), nullable=False, index=True)
    token = Column(String(512), unique=True, nullable=False, index=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    used = Column(Boolean, default=False, nullable=False)
    ip_address = Column(String(45), nullable=True)

    __table_args__ = (
        Index("idx_reset_token_active", "token", "used"),
        Index("idx_reset_user_active", "user_id", "used"),
    )

    def __repr__(self) -> str:
        return f"<PasswordResetToken(id={self.id}, user_id={self.user_id}, used={self.used})>"


class EmailVerificationToken(Base):
    """One-time email verification token."""

    __tablename__ = "email_verification_tokens"

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id = Column(PGUUID(as_uuid=True), nullable=False, index=True)
    token = Column(String(512), unique=True, nullable=False, index=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    used = Column(Boolean, default=False, nullable=False)
    ip_address = Column(String(45), nullable=True)

    __table_args__ = (
        Index("idx_verification_token_active", "token", "used"),
        Index("idx_verification_user_active", "user_id", "used"),
    )

    def __repr__(self) -> str:
        return (
            f"<EmailVerificationToken(id={self.id}, user_id={self.user_id}, used={self.used})>"
        )


__all__ = ["User", "RefreshToken", "PasswordResetToken", "EmailVerificationToken"]