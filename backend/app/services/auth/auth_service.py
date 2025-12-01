"""
Authentication service for user registration, login, and token management.
"""
from datetime import datetime, timedelta
from typing import Optional, Tuple
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from loguru import logger

from app.models.user import User, RefreshToken
from app.core.security import (
    verify_password,
    get_password_hash,
    create_access_token,
    create_refresh_token,
    decode_token,
    validate_password_strength,
    validate_email
)
from app.core.config import settings


class AuthService:
    """Service for handling authentication operations."""
    
    async def register_user(
        self,
        email: str,
        username: str,
        password: str,
        full_name: Optional[str],
        db: AsyncSession
    ) -> Tuple[bool, Optional[User], Optional[str]]:
        """
        Register a new user.
        
        Args:
            email: User email
            username: Username
            password: Plain password
            full_name: Full name (optional)
            db: Database session
            
        Returns:
            Tuple of (success, user, error_message)
        """
        # Validate email
        if not validate_email(email):
            return False, None, "Invalid email format"
        
        # Validate password strength
        is_strong, error = validate_password_strength(password)
        if not is_strong:
            return False, None, error
        
        # Check if email already exists
        result = await db.execute(
            select(User).where(User.email == email)
        )
        if result.scalar_one_or_none():
            return False, None, "Email already registered"
        
        # Check if username already exists
        result = await db.execute(
            select(User).where(User.username == username)
        )
        if result.scalar_one_or_none():
            return False, None, "Username already taken"
        
        # Create user
        try:
            user = User(
                email=email.lower(),
                username=username,
                hashed_password=get_password_hash(password),
                full_name=full_name,
                role="user",
                is_active=True,
                is_verified=False,
                preferences={
                    "theme": "light",
                    "language": "en",
                    "notifications": True
                }
            )
            
            db.add(user)
            await db.commit()
            await db.refresh(user)
            
            logger.info(f"New user registered: {user.email}")
            
            return True, user, None
            
        except Exception as e:
            await db.rollback()
            logger.error(f"User registration failed: {str(e)}")
            return False, None, "Registration failed. Please try again."
    
    async def authenticate_user(
        self,
        email: str,
        password: str,
        db: AsyncSession
    ) -> Tuple[bool, Optional[User], Optional[str]]:
        """
        Authenticate user with email and password.
        
        Args:
            email: User email
            password: Plain password
            db: Database session
            
        Returns:
            Tuple of (success, user, error_message)
        """
        # Get user by email
        result = await db.execute(
            select(User).where(User.email == email.lower())
        )
        user = result.scalar_one_or_none()
        
        if not user:
            return False, None, "Invalid email or password"
        
        # Verify password
        if not verify_password(password, user.hashed_password):
            return False, None, "Invalid email or password"
        
        # Check if account is active
        if not user.is_active:
            return False, None, "Account is deactivated"
        
        # Update last login
        user.last_login = datetime.utcnow()
        await db.commit()
        
        logger.info(f"User authenticated: {user.email}")
        
        return True, user, None
    
    async def create_tokens(
        self,
        user: User,
        db: AsyncSession,
        user_agent: Optional[str] = None,
        ip_address: Optional[str] = None
    ) -> dict:
        """
        Create access and refresh tokens for user.
        
        Args:
            user: User object
            db: Database session
            user_agent: User agent string
            ip_address: IP address
            
        Returns:
            Dictionary with access_token, refresh_token, and metadata
        """
        # Create access token
        access_token = create_access_token(
            data={"sub": str(user.id), "email": user.email, "role": user.role}
        )
        
        # Create refresh token
        refresh_token_str = create_refresh_token(
            data={"sub": str(user.id)}
        )
        
        # Store refresh token in database
        refresh_token = RefreshToken(
            user_id=user.id,
            token=refresh_token_str,
            expires_at=datetime.utcnow() + timedelta(days=settings.refresh_token_expire_days),
            user_agent=user_agent,
            ip_address=ip_address
        )
        
        db.add(refresh_token)
        await db.commit()
        
        return {
            "access_token": access_token,
            "refresh_token": refresh_token_str,
            "token_type": "bearer",
            "expires_in": settings.access_token_expire_minutes * 60,
            "user": user.to_dict()
        }
    
    async def refresh_access_token(
        self,
        refresh_token_str: str,
        db: AsyncSession
    ) -> Tuple[bool, Optional[dict], Optional[str]]:
        """
        Refresh access token using refresh token.
        
        Args:
            refresh_token_str: Refresh token string
            db: Database session
            
        Returns:
            Tuple of (success, tokens_dict, error_message)
        """
        # Decode refresh token
        payload = decode_token(refresh_token_str)
        
        if not payload or payload.get("type") != "refresh":
            return False, None, "Invalid refresh token"
        
        # Get user_id from token
        user_id = payload.get("sub")
        if not user_id:
            return False, None, "Invalid refresh token"
        
        # Check if refresh token exists in database
        result = await db.execute(
            select(RefreshToken).where(
                RefreshToken.token == refresh_token_str,
                RefreshToken.revoked == False
            )
        )
        db_token = result.scalar_one_or_none()
        
        if not db_token:
            return False, None, "Refresh token not found or revoked"
        
        # Check if token is expired
        if db_token.expires_at < datetime.utcnow():
            return False, None, "Refresh token expired"
        
        # Get user
        result = await db.execute(
            select(User).where(User.id == user_id)
        )
        user = result.scalar_one_or_none()
        
        if not user or not user.is_active:
            return False, None, "User not found or inactive"
        
        # Create new access token
        access_token = create_access_token(
            data={"sub": str(user.id), "email": user.email, "role": user.role}
        )
        
        return True, {
            "access_token": access_token,
            "token_type": "bearer",
            "expires_in": settings.access_token_expire_minutes * 60
        }, None
    
    async def revoke_refresh_token(
        self,
        refresh_token_str: str,
        db: AsyncSession
    ) -> bool:
        """
        Revoke a refresh token (logout).
        
        Args:
            refresh_token_str: Refresh token to revoke
            db: Database session
            
        Returns:
            True if revoked successfully
        """
        result = await db.execute(
            select(RefreshToken).where(RefreshToken.token == refresh_token_str)
        )
        token = result.scalar_one_or_none()
        
        if token:
            token.revoked = True
            await db.commit()
            logger.info(f"Refresh token revoked for user {token.user_id}")
            return True
        
        return False
    
    async def update_user_profile(
        self,
        user_id: UUID,
        full_name: Optional[str],
        avatar_url: Optional[str],
        preferences: Optional[dict],
        metadata: Optional[dict],
        db: AsyncSession
    ) -> Tuple[bool, Optional[User], Optional[str]]:
        """
        Update user profile information.
        
        Args:
            user_id: User ID
            full_name: New full name
            avatar_url: New avatar URL
            preferences: User preferences
            metadata: User metadata
            db: Database session
            
        Returns:
            Tuple of (success, user, error_message)
        """
        result = await db.execute(
            select(User).where(User.id == user_id)
        )
        user = result.scalar_one_or_none()
        
        if not user:
            return False, None, "User not found"
        
        try:
            if full_name is not None:
                user.full_name = full_name
            
            if avatar_url is not None:
                user.avatar_url = avatar_url
            
            if preferences is not None:
                user.preferences.update(preferences)
            
            if metadata is not None:
                user.metadata.update(metadata)
            
            user.updated_at = datetime.utcnow()
            
            await db.commit()
            await db.refresh(user)
            
            logger.info(f"Profile updated for user {user.email}")
            
            return True, user, None
            
        except Exception as e:
            await db.rollback()
            logger.error(f"Profile update failed: {str(e)}")
            return False, None, "Profile update failed"
    
    async def change_password(
        self,
        user_id: UUID,
        current_password: str,
        new_password: str,
        db: AsyncSession
    ) -> Tuple[bool, Optional[str]]:
        """
        Change user password.
        
        Args:
            user_id: User ID
            current_password: Current password
            new_password: New password
            db: Database session
            
        Returns:
            Tuple of (success, error_message)
        """
        # Get user
        result = await db.execute(
            select(User).where(User.id == user_id)
        )
        user = result.scalar_one_or_none()
        
        if not user:
            return False, "User not found"
        
        # Verify current password
        if not verify_password(current_password, user.hashed_password):
            return False, "Current password is incorrect"
        
        # Validate new password
        is_strong, error = validate_password_strength(new_password)
        if not is_strong:
            return False, error
        
        try:
            user.hashed_password = get_password_hash(new_password)
            user.updated_at = datetime.utcnow()
            
            await db.commit()
            
            logger.info(f"Password changed for user {user.email}")
            
            return True, None
            
        except Exception as e:
            await db.rollback()
            logger.error(f"Password change failed: {str(e)}")
            return False, "Password change failed"


# Global instance
auth_service = AuthService()

__all__ = ['AuthService', 'auth_service']