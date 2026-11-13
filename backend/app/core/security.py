"Security utilities for authentication and password management."

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Optional, Dict, Any

from jose import JWTError, jwt
from passlib.context import CryptContext
from loguru import logger

from app.core.config import settings


# Password hashing:
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

class TokenType(str, Enum):
    ACCESS = "access"
    REFRESH = "refresh"


# Compiled once — cheap and thread-safe
_EMAIL_RE = re.compile(
    r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$"
)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain password against a bcrypt hash."""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Hash a plain-text password with bcrypt."""
    return pwd_context.hash(password)


def _require_secret_key() -> str:
    """Return the secret key or raise loudly if not configured."""
    key = settings.secret_key
    if not key:
        raise ValueError(
            "SECRET_KEY is not configured. "
            "Set the SECRET_KEY environment variable before starting the server."
        )
    return key


def create_access_token(
    data: Dict[str, Any],
    expires_delta: Optional[timedelta] = None,
) -> str:
    """
    Create a signed JWT access token.

    Args:
        data: Payload to encode (must include 'sub').
        expires_delta: Override default expiry (ACCESS_TOKEN_EXPIRE_MINUTES).

    Returns:
        Encoded JWT string.
    """
    secret = _require_secret_key()
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta
        or timedelta(minutes=settings.access_token_expire_minutes)
    )
    to_encode.update({"exp": expire, "type": TokenType.ACCESS})
    return jwt.encode(to_encode, secret, algorithm=settings.algorithm)


def create_refresh_token(
    data: Dict[str, Any],
    expires_delta: Optional[timedelta] = None,
) -> str:
    """
    Create a signed JWT refresh token.

    Args:
        data: Payload to encode (must include 'sub').
        expires_delta: Override default expiry (REFRESH_TOKEN_EXPIRE_DAYS).

    Returns:
        Encoded JWT string.
    """
    secret = _require_secret_key()
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta
        or timedelta(days=settings.refresh_token_expire_days)
    )
    to_encode.update({"exp": expire, "type": TokenType.REFRESH})
    return jwt.encode(to_encode, secret, algorithm=settings.algorithm)


def decode_token(token: str) -> Optional[Dict[str, Any]]:
    """
    Decode and verify a JWT token.

    Returns the payload dict, or None on any verification failure.
    Callers must check `payload["type"]` to distinguish access vs refresh.
    """
    secret = settings.secret_key
    if not secret:
        logger.error("decode_token called but SECRET_KEY is not set")
        return None
    try:
        payload: Dict[str, Any] = jwt.decode(
            token,
            secret,
            algorithms=[settings.algorithm],
        )
        return payload
    except JWTError as e:
        logger.warning(f"Token decode error: {e}")
        return None


def validate_password_strength(password: str) -> tuple[bool, Optional[str]]:
    """
    Enforce password strength requirements.

    Rules:
      - At least 8 characters
      - At least one uppercase letter
      - At least one lowercase letter
      - At least one digit
      - At least one special character from the allowed set

    Returns:
        (is_valid, error_message)  — error_message is None on success.
    """
    if len(password) < 8:
        return False, "Password must be at least 8 characters long"
    if not any(c.isupper() for c in password):
        return False, "Password must contain at least one uppercase letter"
    if not any(c.islower() for c in password):
        return False, "Password must contain at least one lowercase letter"
    if not any(c.isdigit() for c in password):
        return False, "Password must contain at least one digit"
    special_chars = "!@#$%^&*()_+-=[]{}|;:,.<>?"
    if not any(c in special_chars for c in password):
        return False, "Password must contain at least one special character"
    return True, None


def validate_email(email: str) -> bool:
    """
    Validate e-mail address format (RFC-5321 relaxed).

    Uses a pre-compiled regex — safe to call in hot paths.
    """
    return bool(_EMAIL_RE.match(email))


__all__ = [
    "TokenType",
    "verify_password",
    "get_password_hash",
    "create_access_token",
    "create_refresh_token",
    "decode_token",
    "validate_password_strength",
    "validate_email",
]