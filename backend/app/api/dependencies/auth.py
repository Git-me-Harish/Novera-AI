""" Authentication dependencies for FastAPI endpoints """
from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.organization import Organization
from app.models.user import User
from app.core.security import decode_token, TokenType


# HTTP Bearer scheme — auto_error=True is the default and correct here
security = HTTPBearer()
security_optional = HTTPBearer(auto_error=False)


def _parse_uuid(value: str, label: str = "ID") -> UUID:
    """Parse a string to UUID, raising 400 on failure."""
    try:
        return UUID(value)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid {label} format",
        )


def _credentials_error() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    Validate JWT and return the authenticated User.

    Raises:
        401 — missing / invalid / expired token
        403 — account is inactive
    """
    payload = decode_token(credentials.credentials)
    if payload is None:
        raise _credentials_error()

    # FIX: strict type check — only access tokens are accepted here
    if payload.get("type") != TokenType.ACCESS:
        raise _credentials_error()

    user_id_str: Optional[str] = payload.get("sub")
    if not user_id_str:
        raise _credentials_error()

    user_id = _parse_uuid(user_id_str, "user ID in token")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if user is None:
        raise _credentials_error()

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive",
        )

    return user


async def get_current_active_user(
    current_user: User = Depends(get_current_user),
) -> User:
    """Alias for get_current_user — use where you want to be explicit."""
    return current_user


async def get_verified_user(
    current_user: User = Depends(get_current_user),
) -> User:
    """
    Require e-mail to be verified.
    Use on any endpoint that sends user-initiated data (uploads, profile edits).
    """
    if not current_user.is_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Email verification required. Check your inbox.",
        )
    return current_user


async def get_current_admin_user(
    current_user: User = Depends(get_current_user),
) -> User:
    """Require admin-level role (admin, org_admin, or super_admin)."""
    if not current_user.is_admin():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions. Admin access required.",
        )
    return current_user


async def get_current_super_admin(
    current_user: User = Depends(get_current_user),
) -> User:
    """Require super_admin role."""
    if not current_user.is_super_admin():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Super admin access required",
        )
    return current_user


async def get_current_org_admin(
    current_user: User = Depends(get_current_user),
) -> User:
    """Require org_admin or super_admin role."""
    if not current_user.is_org_admin() and not current_user.is_super_admin():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Organization admin access required",
        )
    return current_user


async def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_optional),
    db: AsyncSession = Depends(get_db),
) -> Optional[User]:
    """
    Return the authenticated user if a valid Bearer token is present,
    otherwise return None.  Use on endpoints that work both authenticated
    and anonymously.
    """
    if credentials is None:
        return None
    try:
        return await get_current_user(credentials, db)
    except HTTPException:
        return None


async def verify_organization_access(
    organization_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Organization:
    """
    Verify the current user has access to the given organization.
    Super admins can access any org; all others are restricted to their own.

    Returns:
        Organization object if access is granted.
    """
    org_uuid = _parse_uuid(organization_id, "organization ID")

    result = await db.execute(
        select(Organization).where(Organization.id == org_uuid)
    )
    organization = result.scalar_one_or_none()

    if not organization:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found",
        )

    if current_user.is_super_admin():
        return organization

    if current_user.organization_id != org_uuid:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this organization",
        )

    return organization


async def verify_user_in_organization(
    user_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    Verify the target user belongs to the same org as the current user.
    Super admins can target any user.

    Returns:
        Target User object if access is granted.
    """
    target_uuid = _parse_uuid(user_id, "user ID")

    result = await db.execute(select(User).where(User.id == target_uuid))
    target_user = result.scalar_one_or_none()

    if not target_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    if current_user.is_super_admin():
        return target_user

    if target_user.organization_id != current_user.organization_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this user",
        )

    return target_user


__all__ = [
    "get_current_user",
    "get_current_active_user",
    "get_verified_user",
    "get_current_admin_user",
    "get_optional_user",
    "get_current_super_admin",
    "get_current_org_admin",
    "verify_organization_access",
    "verify_user_in_organization",
]