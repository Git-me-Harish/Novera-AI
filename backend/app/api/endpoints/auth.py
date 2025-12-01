"""
Authentication API endpoints.
Handles registration, login, logout, token refresh, and password management.
"""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, EmailStr, Field

from app.db.session import get_db
from app.services.auth.auth_service import auth_service
from app.api.dependencies.auth import get_current_user, get_current_active_user
from app.models.user import User


router = APIRouter()


# Request Models
class RegisterRequest(BaseModel):
    """User registration request."""
    email: EmailStr
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=8)
    full_name: Optional[str] = None


class LoginRequest(BaseModel):
    """User login request."""
    email: EmailStr
    password: str


class RefreshTokenRequest(BaseModel):
    """Token refresh request."""
    refresh_token: str


class ChangePasswordRequest(BaseModel):
    """Password change request."""
    current_password: str
    new_password: str = Field(..., min_length=8)


class UpdateProfileRequest(BaseModel):
    """Profile update request."""
    full_name: Optional[str] = None
    avatar_url: Optional[str] = None
    preferences: Optional[dict] = None
    metadata: Optional[dict] = None


# Response Models
class TokenResponse(BaseModel):
    """Token response."""
    access_token: str
    refresh_token: Optional[str] = None
    token_type: str
    expires_in: int
    user: dict


class UserResponse(BaseModel):
    """User data response."""
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
    preferences: dict
    metadata: dict


@router.post("/auth/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(
    request: RegisterRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Register a new user account.
    
    Requirements:
    - Unique email and username
    - Password must be at least 8 characters
    - Password must contain uppercase, lowercase, digit, and special character
    
    Returns access and refresh tokens upon successful registration.
    """
    success, user, error = await auth_service.register_user(
        email=request.email,
        username=request.username,
        password=request.password,
        full_name=request.full_name,
        db=db
    )
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error
        )
    
    # Create tokens for newly registered user
    tokens = await auth_service.create_tokens(user, db)
    
    return tokens


@router.post("/auth/login", response_model=TokenResponse)
async def login(
    request: LoginRequest,
    http_request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    Login with email and password.
    
    Returns access and refresh tokens upon successful authentication.
    """
    success, user, error = await auth_service.authenticate_user(
        email=request.email,
        password=request.password,
        db=db
    )
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=error,
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Get client info
    user_agent = http_request.headers.get("user-agent")
    ip_address = http_request.client.host if http_request.client else None
    
    # Create tokens
    tokens = await auth_service.create_tokens(
        user,
        db,
        user_agent=user_agent,
        ip_address=ip_address
    )
    
    return tokens


@router.post("/auth/refresh", response_model=dict)
async def refresh_token(
    request: RefreshTokenRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Refresh access token using refresh token.
    
    Returns a new access token.
    """
    success, tokens, error = await auth_service.refresh_access_token(
        refresh_token_str=request.refresh_token,
        db=db
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
    db: AsyncSession = Depends(get_db)
):
    """
    Logout user by revoking refresh token.
    """
    await auth_service.revoke_refresh_token(request.refresh_token, db)
    
    return {"message": "Logged out successfully"}


@router.get("/auth/me", response_model=UserResponse)
async def get_current_user_info(
    current_user: User = Depends(get_current_active_user)
):
    """
    Get current authenticated user information.
    """
    return current_user.to_dict()


@router.put("/auth/profile", response_model=UserResponse)
async def update_profile(
    request: UpdateProfileRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Update user profile information.
    """
    success, user, error = await auth_service.update_user_profile(
        user_id=current_user.id,
        full_name=request.full_name,
        avatar_url=request.avatar_url,
        preferences=request.preferences,
        metadata=request.metadata,
        db=db
    )
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error
        )
    
    return user.to_dict()


@router.post("/auth/change-password")
async def change_password(
    request: ChangePasswordRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Change user password.
    
    Requires current password for verification.
    """
    success, error = await auth_service.change_password(
        user_id=current_user.id,
        current_password=request.current_password,
        new_password=request.new_password,
        db=db
    )
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error
        )
    
    return {"message": "Password changed successfully"}


@router.get("/auth/test")
async def test_auth():
    """
    Test endpoint to verify authentication API is working.
    """
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
            "POST /auth/change-password"
        ]
    }


__all__ = ['router']