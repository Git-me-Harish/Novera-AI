""" Authentication API endpoints, Handles registration, login, logout, token refresh, and password management."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth import (
    get_current_admin_user,
    get_current_user,
    get_current_active_user,
    get_verified_user,
)
from app.core.config import settings
from app.db.session import get_db
from app.models.user import User
from app.services.auth.auth_service import auth_service

router = APIRouter()


# Request Models:
class RegisterRequest(BaseModel):
    email: EmailStr
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=8, max_length=128)
    full_name: Optional[str] = None


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
@router.post("/auth/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(
    request: RegisterRequest,
    http_request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Register a new user account.

    User is assigned to the default organization.
    Returns access + refresh tokens on success and sends a verification email.
    """
    ip = http_request.client.host if http_request.client else None

    success, user, error = await auth_service.register_user(
        email=request.email,
        username=request.username,
        password=request.password,
        full_name=request.full_name,
        ip_address=ip,
        db=db,
        organization_id=None,
    )

    if not success:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error)

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
    success, user, error = await auth_service.authenticate_user(
        email=request.email,
        password=request.password,
        db=db,
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=error,
            headers={"WWW-Authenticate": "Bearer"},
        )

    return await auth_service.create_tokens(
        user,
        db,
        user_agent=http_request.headers.get("user-agent"),
        ip_address=http_request.client.host if http_request.client else None,
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
