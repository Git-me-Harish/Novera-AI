"""
Authentication API endpoints.
Handles registration, login, logout, token refresh, and password management.
"""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, EmailStr, Field
from loguru import logger

from app.db.session import get_db
from app.services.auth.auth_service import auth_service
from app.api.dependencies.auth import get_current_user, get_current_active_user
from app.models.user import User
from fastapi import BackgroundTasks


router = APIRouter()

# ---------------------------
# Request Models
# ---------------------------

class RegisterRequest(BaseModel):
    email: EmailStr
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=8)
    full_name: Optional[str] = None

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class RefreshTokenRequest(BaseModel):
    refresh_token: str

class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(..., min_length=8)

class UpdateProfileRequest(BaseModel):
    full_name: Optional[str] = None
    avatar_url: Optional[str] = None
    preferences: Optional[dict] = None
    metadata: Optional[dict] = None

class ForgotPasswordRequest(BaseModel):
    email: EmailStr

class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(..., min_length=8)

class VerifyResetTokenRequest(BaseModel):
    token: str

class VerifyEmailRequest(BaseModel):
    token: str

# ---------------------------
# Response Models
# ---------------------------

class TokenResponse(BaseModel):
    access_token: str
    refresh_token: Optional[str] = None
    token_type: str
    expires_in: int
    user: dict

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
    preferences: dict = {}
    metadata: dict = {}

# ---------------------------
# Routes
# ---------------------------

@router.post("/auth/register", response_model=TokenResponse, status_code=201)
async def register(
    request: RegisterRequest,
    http_request: Request,
    db: AsyncSession = Depends(get_db)
):
    ip_address = http_request.client.host if http_request.client else None

    success, user, error = await auth_service.register_user(
        email=request.email,
        username=request.username,
        password=request.password,
        full_name=request.full_name,
        ip_address=ip_address,
        db=db,
    )

    if not success:
        raise HTTPException(status_code=400, detail=error)

    tokens = await auth_service.create_tokens(user, db)
    return TokenResponse(**tokens)

# ---------------------------

@router.post("/auth/login", response_model=TokenResponse)
async def login(
    request: LoginRequest,
    http_request: Request,
    db: AsyncSession = Depends(get_db)
):
    """Login with email and password."""
    try:
        success, user, error = await auth_service.authenticate_user(
            email=request.email,
            password=request.password,
            db=db
        )
        if not success:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=error)

        user_agent = http_request.headers.get("user-agent")
        ip_address = http_request.client.host if http_request.client else None

        tokens = await auth_service.create_tokens(
            user, db, user_agent=user_agent, ip_address=ip_address
        )
        return TokenResponse(**tokens)

    except Exception as e:
        logger.exception("Error during login")
        raise HTTPException(status_code=500, detail="Internal server error")

# ---------------------------

@router.post("/auth/send-verification")
async def send_verification(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    ip_address = request.client.host if request.client else None

    success, error = await auth_service.send_verification_email(
        user_id=current_user.id,
        email=current_user.email,
        username=current_user.username,
        ip_address=ip_address,
        db=db
    )

    if not success:
        raise HTTPException(status_code=400, detail=error)

    return {"message": "Verification email sent"}

@router.post("/auth/refresh", response_model=TokenResponse)
async def refresh_token(
    request: RefreshTokenRequest,
    db: AsyncSession = Depends(get_db)
):
    """Refresh access token using refresh token."""
    try:
        success, tokens, error = await auth_service.refresh_access_token(
            refresh_token_str=request.refresh_token, db=db
        )
        if not success:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=error)
        return TokenResponse(**tokens)
    except Exception as e:
        logger.exception("Error refreshing token")
        raise HTTPException(status_code=500, detail="Internal server error")

# ---------------------------

@router.post("/auth/logout")
async def logout(
    request: RefreshTokenRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Logout user by revoking refresh token."""
    try:
        await auth_service.revoke_refresh_token(request.refresh_token, db)
        return {"message": "Logged out successfully"}
    except Exception as e:
        logger.exception("Error during logout")
        raise HTTPException(status_code=500, detail="Internal server error")

# ---------------------------

@router.get("/auth/me", response_model=UserResponse)
async def get_current_user_info(
    current_user: User = Depends(get_current_active_user)
):
    """Get current authenticated user information."""
    try:
        return UserResponse(**current_user.to_dict())
    except Exception as e:
        logger.exception("Error fetching user info")
        raise HTTPException(status_code=500, detail="Internal server error")

# ---------------------------

@router.put("/auth/profile", response_model=UserResponse)
async def update_profile(
    request: UpdateProfileRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Update user profile information."""
    try:
        success, user, error = await auth_service.update_user_profile(
            user_id=current_user.id,
            full_name=request.full_name,
            avatar_url=request.avatar_url,
            preferences=request.preferences or {},
            metadata=request.metadata or {},
            db=db
        )
        if not success:
            raise HTTPException(status_code=400, detail=error)
        return UserResponse(**user.to_dict())
    except Exception as e:
        logger.exception("Error updating profile")
        raise HTTPException(status_code=500, detail="Internal server error")

# ---------------------------

@router.post("/auth/change-password")
async def change_password(
    request: ChangePasswordRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Change user password."""
    try:
        success, error = await auth_service.change_password(
            user_id=current_user.id,
            current_password=request.current_password,
            new_password=request.new_password,
            db=db
        )
        if not success:
            raise HTTPException(status_code=400, detail=error)
        return {"message": "Password changed successfully"}
    except Exception as e:
        logger.exception("Error changing password")
        raise HTTPException(status_code=500, detail="Internal server error")

# ---------------------------

@router.post("/auth/forgot-password")
async def forgot_password(
    request: ForgotPasswordRequest,
    http_request: Request,
    background_tasks: BackgroundTasks,  # <-- add this
    db: AsyncSession = Depends(get_db)
):
    ip_address = http_request.client.host if http_request.client else None
    success, error = await auth_service.request_password_reset(
        email=request.email,
        ip_address=ip_address,
        db=db,
        background_tasks=background_tasks  # <-- pass BackgroundTasks
    )
    if not success and error:
        raise HTTPException(status_code=400, detail=error)
    return {"message": "If the email exists, a password reset link has been sent", "email": request.email}


# ---------------------------

@router.post("/auth/verify-reset-token")
async def verify_reset_token(
    request: VerifyResetTokenRequest,
    db: AsyncSession = Depends(get_db)
):
    """Verify password reset token."""
    try:
        is_valid, user_id, error = await auth_service.verify_reset_token(token=request.token, db=db)
        if not is_valid:
            raise HTTPException(status_code=400, detail=error)
        return {"valid": True, "message": "Token is valid"}
    except Exception as e:
        logger.exception("Error verifying reset token")
        raise HTTPException(status_code=500, detail="Internal server error")

# ---------------------------

@router.post("/auth/reset-password")
async def reset_password(
    request: ResetPasswordRequest,
    db: AsyncSession = Depends(get_db)
):
    """Reset password using reset token."""
    try:
        success, error = await auth_service.reset_password(token=request.token, new_password=request.new_password, db=db)
        if not success:
            raise HTTPException(status_code=400, detail=error)
        return {"message": "Password reset successfully"}
    except Exception as e:
        logger.exception("Error resetting password")
        raise HTTPException(status_code=500, detail="Internal server error")

# ---------------------------

@router.post("/auth/verify-email")
async def verify_email(
    request: VerifyEmailRequest,
    db: AsyncSession = Depends(get_db)
):
    """Verify user's email address using verification token."""
    try:
        success, error = await auth_service.verify_email(token=request.token, db=db)
        if not success:
            raise HTTPException(status_code=400, detail=error)
        return {"message": "Email verified successfully", "verified": True}
    except Exception as e:
        logger.exception("Error verifying email")
        raise HTTPException(status_code=500, detail="Internal server error")

# ---------------------------

@router.post("/auth/resend-verification")
async def resend_verification(
    http_request: Request,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    if current_user.is_verified:
        raise HTTPException(status_code=400, detail="Email already verified")

    ip_address = http_request.client.host if http_request.client else None

    success, error = await auth_service.resend_verification_email(
        user_id=current_user.id,
        ip_address=ip_address,
        db=db,
        background_tasks=background_tasks
    )

    if not success:
        raise HTTPException(status_code=400, detail=error)

    return {"message": "Verification email sent"}

# ---------------------------
# Test endpoint
# ---------------------------

@router.get("/auth/test")
async def test_auth():
    """Test endpoint to verify authentication API is working."""
    return {
        "status": "operational",
        "message": "Authentication API is ready",
        "endpoints": [
            "POST /auth/register",
            "POST /auth/login",
            "POST /auth/refresh",
            "POST /auth/logout",
            "GET /auth/me",
            "PUT /auth/profile",
            "POST /auth/change-password",
            "POST /auth/forgot-password",
            "POST /auth/verify-reset-token",
            "POST /auth/reset-password",
            "POST /auth/verify-email",
            "POST /auth/resend-verification"
        ]
    }

__all__ = ['router']
