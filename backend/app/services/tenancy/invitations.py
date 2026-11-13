"""Invitation-based organization membership."""
from __future__ import annotations

import asyncio
import hashlib
import html
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from uuid import UUID

from loguru import logger
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import get_password_hash, validate_password_strength
from app.models.organization import Organization
from app.models.tenancy import OrganizationInvitation
from app.models.user import User
from app.services.tenancy import quotas
from app.services.tenancy.roles import assert_can_grant

INVITABLE_ROLES = ("user", "admin", "org_admin")


class InvitationError(ValueError):
    pass


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def invitation_url(token: str) -> str:
    return f"{settings.frontend_url.rstrip('/')}/accept-invite?token={token}"


def invitation_dict(inv: OrganizationInvitation) -> dict[str, Any]:
    return {
        "id": str(inv.id),
        "email": inv.email,
        "role": inv.role,
        "status": inv.status,
        "created_at": inv.created_at.isoformat(),
        "expires_at": inv.expires_at.isoformat(),
        "accepted_at": inv.accepted_at.isoformat() if inv.accepted_at else None,
        "revoked_at": inv.revoked_at.isoformat() if inv.revoked_at else None,
        "invited_by": str(inv.invited_by) if inv.invited_by else None,
    }


async def create(
    db: AsyncSession, *, actor: User, organization_id: UUID, email: str, role: str = "user"
) -> tuple[OrganizationInvitation, str]:
    """Create an invitation and return it with the one-time token."""
    email = email.strip().lower()
    if role not in INVITABLE_ROLES:
        raise InvitationError("Invalid role")
    assert_can_grant(actor, role)
    if (await db.execute(select(User.id).where(func.lower(User.email) == email))).first():
        # Accounts belong to exactly one organization.
        raise InvitationError("This email already has an account")
    if (await db.execute(select(OrganizationInvitation.id).where(
        OrganizationInvitation.organization_id == organization_id,
        func.lower(OrganizationInvitation.email) == email,
        OrganizationInvitation.accepted_at.is_(None),
        OrganizationInvitation.revoked_at.is_(None),
        OrganizationInvitation.expires_at > func.now(),
    ))).first():
        raise InvitationError("An invitation for this email is already pending")
    # Expired-but-open invitations would violate the open-invite unique index.
    for stale in (await db.execute(select(OrganizationInvitation).where(
        OrganizationInvitation.organization_id == organization_id,
        func.lower(OrganizationInvitation.email) == email,
        OrganizationInvitation.accepted_at.is_(None),
        OrganizationInvitation.revoked_at.is_(None),
    ))).scalars():
        stale.revoked_at = datetime.now(timezone.utc)
    await quotas.ensure_user_capacity(db, organization_id, count_pending_invitations=True)

    token = secrets.token_urlsafe(32)
    invitation = OrganizationInvitation(
        organization_id=organization_id,
        email=email,
        role=role,
        token_hash=_hash(token),
        invited_by=actor.id,
        created_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc) + timedelta(days=settings.invitation_expire_days),
    )
    db.add(invitation)
    await db.flush()
    return invitation, token


async def find_open(db: AsyncSession, token: str, *, lock: bool = False) -> OrganizationInvitation:
    query = select(OrganizationInvitation).where(OrganizationInvitation.token_hash == _hash(token))
    if lock:
        query = query.with_for_update()
    invitation = (await db.execute(query)).scalar_one_or_none()
    if invitation is None or invitation.status != "pending":
        # One message for missing/used/revoked/expired: no token oracle.
        raise InvitationError("This invitation is invalid or has expired")
    return invitation


async def accept(
    db: AsyncSession, *, token: str, username: str, password: str, full_name: Optional[str]
) -> tuple[User, OrganizationInvitation]:
    invitation = await find_open(db, token, lock=True)
    org = (await db.execute(
        select(Organization).where(Organization.id == invitation.organization_id)
    )).scalar_one()
    if not org.is_active:
        raise InvitationError("This organization is not active")
    strong, problem = validate_password_strength(password)
    if not strong:
        raise InvitationError(problem or "Password is too weak")
    if (await db.execute(select(User.id).where(func.lower(User.email) == invitation.email))).first():
        raise InvitationError("This email already has an account")
    if (await db.execute(select(User.id).where(User.username == username))).first():
        raise InvitationError("Username already taken")
    await quotas.ensure_user_capacity(db, invitation.organization_id)

    user = User(
        email=invitation.email,
        username=username,
        hashed_password=get_password_hash(password),
        full_name=full_name,
        role=invitation.role,
        is_active=True,
        # The invitation link went to this address, so ownership is proven.
        is_verified=True,
        organization_id=invitation.organization_id,
        preferences={"theme": "light", "language": "en", "notifications": True},
    )
    db.add(user)
    await db.flush()
    invitation.accepted_at = datetime.now(timezone.utc)
    invitation.accepted_user_id = user.id
    return user, invitation


async def send_email(invitation: OrganizationInvitation, token: str, organization_name: str,
                     inviter_name: str) -> bool:
    """Best effort: returns False when SMTP is not configured or fails."""
    if not settings.smtp_user:
        return False
    from app.services.email.email_service import email_service

    link = invitation_url(token)
    org = html.escape(organization_name)
    inviter = html.escape(inviter_name)
    body = (
        f"<p>{inviter} invited you to join <strong>{org}</strong> on Novera.</p>"
        f'<p><a href="{html.escape(link)}">Accept the invitation</a></p>'
        f"<p>This link expires in {settings.invitation_expire_days} days and can be used once.</p>"
    )
    text = f"{inviter_name} invited you to join {organization_name} on Novera.\n\nAccept: {link}\n"
    try:
        # smtplib blocks; never run it on the event loop.
        return await asyncio.to_thread(
            email_service.send_email, invitation.email, f"Join {organization_name} on Novera", body, text
        )
    except Exception as exc:
        logger.error(f"Invitation email failed: {type(exc).__name__}")
        return False
