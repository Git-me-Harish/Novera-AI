"""Session refresh, password reset and email verification against real PostgreSQL.

All three compared timezone-aware DB timestamps with naive ``utcnow()`` and
raised TypeError (HTTP 500) on every call. These tests pin the working flows,
including the expired-token branches.
"""
import secrets
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import delete, select, text, update

from app.db.session import AsyncSessionLocal, engine
from app.models.organization import Organization
from app.models.user import EmailVerificationToken, PasswordResetToken, RefreshToken, User
from app.services.auth.auth_service import auth_service


@pytest.fixture
async def user():
    await engine.dispose()
    try:
        async with AsyncSessionLocal() as db:
            await db.execute(text("SELECT 1 FROM refresh_tokens LIMIT 1"))
    except Exception as exc:  # pragma: no cover - environment dependent
        pytest.skip(f"PostgreSQL with migrations not available: {type(exc).__name__}")
    tag = uuid4().hex[:10]
    org = Organization(id=uuid4(), name=f"auth-{tag}", slug=f"auth-{tag}", display_name="A")
    account = User(id=uuid4(), email=f"auth-{tag}@example.invalid", username=f"auth-{tag}",
                   hashed_password="x", organization_id=org.id, is_active=True)
    async with AsyncSessionLocal() as db:
        db.add(org)
        await db.flush()
        db.add(account)
        await db.commit()
    yield account
    async with AsyncSessionLocal() as db:
        for model in (RefreshToken, PasswordResetToken, EmailVerificationToken):
            await db.execute(delete(model).where(model.user_id == account.id))
        await db.execute(delete(User).where(User.id == account.id))
        await db.execute(delete(Organization).where(Organization.id == org.id))
        await db.commit()
    await engine.dispose()


async def test_refresh_issues_a_new_access_token_and_rejects_expired(user):
    async with AsyncSessionLocal() as db:
        tokens = await auth_service.create_tokens(user, db)
        ok, refreshed, error = await auth_service.refresh_access_token(tokens["refresh_token"], db)
        assert ok and refreshed["access_token"] and error is None

        await db.execute(update(RefreshToken).where(RefreshToken.token == tokens["refresh_token"])
                         .values(expires_at=datetime.now(timezone.utc) - timedelta(minutes=1)))
        await db.commit()
        ok, refreshed, error = await auth_service.refresh_access_token(tokens["refresh_token"], db)
    assert not ok and refreshed is None and "expired" in error.lower()


async def test_password_reset_token_valid_and_expired(user):
    valid, expired = secrets.token_urlsafe(16), secrets.token_urlsafe(16)
    now = datetime.now(timezone.utc)
    async with AsyncSessionLocal() as db:
        db.add_all([
            PasswordResetToken(user_id=user.id, token=valid, expires_at=now + timedelta(minutes=15)),
            PasswordResetToken(user_id=user.id, token=expired, expires_at=now - timedelta(minutes=1)),
        ])
        await db.commit()
        ok, user_id, _ = await auth_service.verify_reset_token(valid, db)
        assert ok and user_id == user.id
        ok, user_id, error = await auth_service.verify_reset_token(expired, db)
    assert not ok and user_id is None and error


async def test_email_verification_valid_and_expired(user):
    valid, expired = secrets.token_urlsafe(16), secrets.token_urlsafe(16)
    now = datetime.now(timezone.utc)
    async with AsyncSessionLocal() as db:
        db.add_all([
            EmailVerificationToken(user_id=user.id, token=expired, expires_at=now - timedelta(hours=1)),
            EmailVerificationToken(user_id=user.id, token=valid, expires_at=now + timedelta(hours=24)),
        ])
        await db.commit()
        ok, error = await auth_service.verify_email(expired, db)
        assert not ok and error
        ok, error = await auth_service.verify_email(valid, db)
        assert ok, error
        verified = (await db.execute(select(User.is_verified).where(User.id == user.id))).scalar_one()
    assert verified
