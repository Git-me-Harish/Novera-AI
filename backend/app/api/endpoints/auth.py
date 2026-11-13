""" Authentication API endpoints, Handles registration, login, logout, token refresh, and password management."""
from __future__ import annotations

import hashlib
import re
import secrets
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth import (
    get_current_admin_user,
    get_current_user,
    get_current_active_user,
    get_verified_user,
)
from app.core.config import settings
from app.db.session import get_db
from app.core.net import client_ip
from app.models.organization import Organization
from app.models.user import User
from app.services.auth.auth_service import auth_service
from app.services.tenancy import audit
from app.services.tenancy.audit import Action

router = APIRouter()

_LOGIN_FAILURES_PER_ACCOUNT = 10
_LOGIN_FAILURE_WINDOW_SECONDS = 900


# Request Models:
class RegisterRequest(BaseModel):
    email: EmailStr
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=8, max_length=128)
    full_name: Optional[str] = None
    # self_serve mode only: name of the new organization.
    organization_name: Optional[str] = Field(None, max_length=200)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(..., min_length=8, max_length=128)


class UpdateProfileRequest(BaseModel):
    full_name: Optional[str] = None
    avatar_url: Optional[str] = None
    preferences: Optional[dict] = None
    metadata: Optional[dict] = None


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(..., min_length=8, max_length=128)


class VerifyResetTokenRequest(BaseModel):
    token: str


class VerifyEmailRequest(BaseModel):
    token: str


# Response Models

class TokenResponse(BaseModel):
    access_token: str
    refresh_token: Optional[str] = None
    token_type: str
    expires_in: int
    user: dict


class TokenRefreshResponse(BaseModel):
    access_token: str
    token_type: str
    expires_in: int


class UserResponse(BaseModel):
    id: str
    email: str
    username: str
    full_name: Optional[str]
    avatar_url: Optional[str]
    role: str
    is_active: bool
    is_verified: bool
    created_at: str
    last_login: Optional[str]
    preferences: Optional[dict] = {}
    metadata: Optional[dict] = {}


# Endpoints:
@router.get("/auth/registration-mode")
async def registration_mode():
    """Lets the sign-up page show the right flow (or none)."""
    return {"mode": settings.registration_mode}


@router.post("/auth/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(
    request: RegisterRequest,
    http_request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Self-registration, governed by REGISTRATION_MODE.

    A sign-up never joins an existing organization: that used to place any
    stranger inside the shared "default" tenant with access to its documents.
    ``self_serve`` creates a new organization owned by the new user;
    ``invite_only`` and ``disabled`` refuse (people join via invitations).
    """
    if settings.registration_mode != "self_serve":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Registration is by invitation only. Ask your administrator for an invite."
                if settings.registration_mode == "invite_only"
                else "Self-registration is disabled."
            ),
        )
    ip = client_ip(http_request)
    org_name = (request.organization_name or f"{request.username}'s workspace").strip()[:200]
    org = Organization(
        id=uuid4(),
        name=f"{_slug(org_name)}-{secrets.token_hex(3)}",
        slug=f"{_slug(org_name)}-{secrets.token_hex(3)}",
        display_name=org_name,
        is_active=True,
        settings={},
    )
    db.add(org)
    await db.flush()  # visible to register_user; rolled back if sign-up fails

    success, user, error = await auth_service.register_user(
        email=request.email,
        username=request.username,
        password=request.password,
        full_name=request.full_name,
        ip_address=ip,
        db=db,
        organization_id=org.id,
        role="org_admin",
    )
    if not success:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error)

    org.created_by = user.id
    audit.record(db, Action.REGISTERED, actor=user, organization_id=org.id, target_type="organization",
                 target_id=org.id, details={"organization": org.display_name}, request=http_request)
    await db.commit()
    return await auth_service.create_tokens(user, db)


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug[:40] or "workspace"


class InvitationAcceptRequest(BaseModel):
    token: str = Field(..., min_length=20, max_length=200)
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=8, max_length=128)
    full_name: Optional[str] = Field(None, max_length=255)


@router.get("/auth/invitations/{token}")
async def preview_invitation(token: str, db: AsyncSession = Depends(get_db)):
    """What the accept page shows before the user sets a password."""
    from app.services.tenancy import invitations

    try:
        invitation = await invitations.find_open(db, token)
    except invitations.InvitationError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    org = (await db.execute(select(Organization).where(Organization.id == invitation.organization_id))).scalar_one()
    if not org.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="This invitation is invalid or has expired")
    return {
        "email": invitation.email,
        "role": invitation.role,
        "organization": org.display_name,
        "expires_at": invitation.expires_at.isoformat(),
    }


@router.post("/auth/invitations/accept", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def accept_invitation(
    request: InvitationAcceptRequest,
    http_request: Request,
    db: AsyncSession = Depends(get_db),
):
    from app.services.tenancy import invitations
    from app.services.tenancy.quotas import QuotaExceeded

    try:
        user, invitation = await invitations.accept(
            db, token=request.token, username=request.username,
            password=request.password, full_name=request.full_name,
        )
    except invitations.InvitationError as exc:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except QuotaExceeded as exc:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=exc.as_detail())
    audit.record(db, Action.INVITATION_ACCEPTED, actor=user, organization_id=user.organization_id,
                 target_type="invitation", target_id=invitation.id, details={"role": user.role},
                 request=http_request)
    await db.commit()
    await db.refresh(user, ["organization"])
    return await auth_service.create_tokens(user, db)


@router.post("/auth/login", response_model=TokenResponse)
async def login(
    request: LoginRequest,
    http_request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Authenticate with e-mail + password.
    Returns access + refresh tokens on success.
    """
    from app.core.redis_manager import redis_manager

    # Per-account throttle: IP limits cannot stop credential stuffing spread
    # across many addresses. Keyed by a hash so emails never sit in Redis.
    email_key = "login_fail:" + hashlib.sha256(request.email.lower().encode()).hexdigest()
    try:
        recent_failures = int(await redis_manager.get(email_key) or 0)
    except Exception:
        recent_failures = 0
    if recent_failures >= _LOGIN_FAILURES_PER_ACCOUNT:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed sign-in attempts. Try again in 15 minutes or reset your password.",
            headers={"Retry-After": str(_LOGIN_FAILURE_WINDOW_SECONDS)},
        )

    success, user, error = await auth_service.authenticate_user(
        email=request.email,
        password=request.password,
        db=db,
    )

    if not success:
        try:
            await redis_manager.increment(email_key, ttl=_LOGIN_FAILURE_WINDOW_SECONDS)
        except Exception:
            pass
        await audit.record_independent(
            Action.LOGIN_FAILED, outcome="failure", details={"email": request.email.lower(), "reason": error},
            request=http_request,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=error,
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        await redis_manager.delete(email_key)
    except Exception:
        pass
    audit.record(db, Action.LOGIN, actor=user, request=http_request)
    return await auth_service.create_tokens(
        user,
        db,
        user_agent=http_request.headers.get("user-agent"),
        ip_address=client_ip(http_request),
    )


@router.post("/auth/refresh", response_model=TokenRefreshResponse)
async def refresh_token(
    request: RefreshTokenRequest,
    db: AsyncSession = Depends(get_db),
):
    """Exchange a valid refresh token for a new access token."""
    success, tokens, error = await auth_service.refresh_access_token(
        refresh_token_str=request.refresh_token,
        db=db,
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=error,
            headers={"WWW-Authenticate": "Bearer"},
        )

    return tokens


@router.post("/auth/logout")
async def logout(
    request: RefreshTokenRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Revoke the provided refresh token (logout current session)."""
    await auth_service.revoke_refresh_token(request.refresh_token, db)
    return {"message": "Logged out successfully"}


@router.get("/auth/me", response_model=UserResponse)
async def get_current_user_info(
    current_user: User = Depends(get_current_active_user),
):
    """Return the authenticated user's profile including organization info."""
    return current_user.to_dict(include_organization=True)


@router.put("/auth/profile", response_model=UserResponse)
async def update_profile(
    request: UpdateProfileRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Update the current user's profile."""
    success, user, error = await auth_service.update_user_profile(
        user_id=current_user.id,
        full_name=request.full_name,
        avatar_url=request.avatar_url,
        preferences=request.preferences,
        metadata=request.metadata,
        db=db,
    )

    if not success:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error)

    return user.to_dict()


@router.post("/auth/change-password")
async def change_password(
    request: ChangePasswordRequest,
    current_user: User = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Change the current user's password.
    Requires current password for verification and a verified e-mail.
    """
    success, error = await auth_service.change_password(
        user_id=current_user.id,
        current_password=request.current_password,
        new_password=request.new_password,
        db=db,
    )

    if not success:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error)

    return {"message": "Password changed successfully"}


@router.post("/auth/forgot-password")
async def forgot_password(
    request: ForgotPasswordRequest,
    http_request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Request a password-reset link.

    Always returns 200 to prevent e-mail enumeration.
    Only raises 500 on a true server failure.
    """
    ip = http_request.client.host if http_request.client else None

    try:
        await auth_service.request_password_reset(
            email=request.email,
            ip_address=ip,
            db=db,
        )
    except Exception:
        # Log internally but never surface to the caller
        pass

    return {"message": "If the email exists, a password reset link has been sent"}


@router.post("/auth/verify-reset-token")
async def verify_reset_token(
    request: VerifyResetTokenRequest,
    db: AsyncSession = Depends(get_db),
):
    """Validate a password-reset token before showing the reset form."""
    is_valid, user_id, error = await auth_service.verify_reset_token(
        token=request.token,
        db=db,
    )

    if not is_valid:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error)

    return {"valid": True, "message": "Token is valid"}


@router.post("/auth/reset-password")
async def reset_password(
    request: ResetPasswordRequest,
    db: AsyncSession = Depends(get_db),
):
    """Reset password using a valid reset token."""
    success, error = await auth_service.reset_password(
        token=request.token,
        new_password=request.new_password,
        db=db,
    )

    if not success:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error)

    return {"message": "Password reset successfully"}


@router.post("/auth/verify-email")
async def verify_email(
    request: VerifyEmailRequest,
    db: AsyncSession = Depends(get_db),
):
    """Verify a user's e-mail address using the token sent after registration."""
    success, error = await auth_service.verify_email(
        token=request.token,
        db=db,
    )

    if not success:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error)

    return {"message": "Email verified successfully", "verified": True}


@router.post("/auth/resend-verification")
async def resend_verification(
    http_request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Resend the e-mail verification link.
    Only valid for unverified accounts. Rate-limited to 1 request/5 min.
    """
    if current_user.is_verified:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already verified",
        )

    ip = http_request.client.host if http_request.client else None

    success, error = await auth_service.resend_verification_email(
        user_id=current_user.id,
        ip_address=ip,
        db=db,
    )

    if not success:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error)

    return {"message": "Verification email sent", "email": current_user.email}


if settings.debug:
    @router.get("/auth/test")
    async def test_auth(current_user: User = Depends(get_current_admin_user)):
        """Test endpoint — only available in debug/development mode."""
        return {
            "status": "operational",
            "message": "Authentication API is ready",
        }


__all__ = ["router"]
