"""Append-only audit trail for security-relevant actions.

Two ways to record:
  * ``record(db, ...)`` adds the event to the caller's session, so it commits
    atomically with the action it describes (no event without the change,
    no change without the event);
  * ``record_independent(...)`` commits in its own session, for denials and
    failures whose request session will roll back (failed login, quota hit).

Audit failures are logged and never break the request.
"""
from __future__ import annotations

import base64
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any, Optional
from uuid import UUID

from loguru import logger
from sqlalchemy import and_, delete, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

from app.core.net import client_ip
from app.models.tenancy import AuditEvent


class Action:
    LOGIN = "auth.login"
    LOGIN_FAILED = "auth.login_failed"
    LOGOUT = "auth.logout"
    PASSWORD_CHANGED = "auth.password_changed"
    PASSWORD_RESET = "auth.password_reset"
    REGISTERED = "auth.registered"
    USER_CREATED = "user.created"
    USER_UPDATED = "user.updated"
    USER_ROLE_CHANGED = "user.role_changed"
    USER_DEACTIVATED = "user.deactivated"
    USER_REACTIVATED = "user.reactivated"
    USER_DELETED = "user.deleted"
    USER_PASSWORD_RESET_BY_ADMIN = "user.password_reset_by_admin"
    INVITATION_CREATED = "invitation.created"
    INVITATION_REVOKED = "invitation.revoked"
    INVITATION_ACCEPTED = "invitation.accepted"
    ORG_CREATED = "organization.created"
    ORG_UPDATED = "organization.updated"
    ORG_SUSPENDED = "organization.suspended"
    ORG_REACTIVATED = "organization.reactivated"
    ORG_DELETED = "organization.deleted"
    ORG_LIMITS_CHANGED = "organization.limits_changed"
    BRANDING_UPDATED = "organization.branding_updated"
    AI_SETTINGS_UPDATED = "ai_settings.updated"
    AI_SETTINGS_RESET = "ai_settings.reset"
    DOCUMENT_UPLOADED = "document.uploaded"
    DOCUMENT_DELETED = "document.deleted"
    DOCUMENT_REPROCESSED = "document.reprocessed"
    DOCUMENT_UPDATED = "document.updated"
    CHUNK_EDITED = "chunk.edited"
    CHUNK_REVERTED = "chunk.reverted"
    CHUNK_DELETED = "chunk.deleted"
    QUOTA_EXCEEDED = "quota.exceeded"
    ACCESS_DENIED = "access.denied"


_SECRET_KEYS = ("password", "token", "secret", "api_key", "apikey", "authorization", "key")


def _scrub(value: Any) -> Any:
    """Redact anything that looks like a credential, at any depth."""
    if isinstance(value, dict):
        return {
            k: "[redacted]" if any(s in str(k).lower() for s in _SECRET_KEYS) else _scrub(v)
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [_scrub(v) for v in value]
    return value


def _build(
    action: str,
    *,
    organization_id: Any = None,
    actor: Any = None,
    outcome: str = "success",
    target_type: Optional[str] = None,
    target_id: Any = None,
    details: Optional[dict] = None,
    request: Optional[Request] = None,
) -> AuditEvent:
    if organization_id is None and actor is not None:
        organization_id = getattr(actor, "organization_id", None)
    return AuditEvent(
        organization_id=organization_id,
        actor_user_id=getattr(actor, "id", None),
        actor_email=getattr(actor, "email", None),
        actor_role=getattr(actor, "role", None),
        action=action,
        outcome=outcome,
        target_type=target_type,
        target_id=str(target_id) if target_id is not None else None,
        ip_address=client_ip(request)[:45] if request else None,
        user_agent=(request.headers.get("user-agent") or "")[:255] if request else None,
        request_id=getattr(request.state, "request_id", None) if request else None,
        details=json.loads(json.dumps(_scrub(details or {}), default=str)),
    )


def snapshot(user: Any) -> SimpleNamespace:
    """Detached copy of the actor's identity.

    Take it BEFORE rolling back: a rollback expires ORM objects, and reading
    them afterwards on an async session fails, losing the audit event.
    """
    return SimpleNamespace(id=user.id, email=user.email, role=user.role,
                           organization_id=user.organization_id)


def record(db: AsyncSession, action: str, **kwargs: Any) -> None:
    """Add an event to ``db``; it commits together with the caller's change."""
    try:
        db.add(_build(action, **kwargs))
    except Exception as exc:  # pragma: no cover - defensive
        logger.error(f"Audit event {action} not recorded: {type(exc).__name__}")


async def record_independent(action: str, **kwargs: Any) -> None:
    """Commit an event on its own session (survives the caller's rollback).

    The caller must roll back first when it holds row locks (quota checks lock
    the organization row): this insert references that row and would wait on
    the caller's lock forever. Pass ``actor=snapshot(user)`` taken before the
    rollback.
    """
    from app.db.session import AsyncSessionLocal

    try:
        async with AsyncSessionLocal() as db:
            db.add(_build(action, **kwargs))
            await db.commit()
    except Exception as exc:
        logger.error(f"Audit event {action} not recorded: {type(exc).__name__}")


def event_dict(event: AuditEvent) -> dict[str, Any]:
    return {
        "id": str(event.id),
        "created_at": event.created_at.isoformat(),
        "organization_id": str(event.organization_id) if event.organization_id else None,
        "actor_user_id": str(event.actor_user_id) if event.actor_user_id else None,
        "actor_email": event.actor_email,
        "actor_role": event.actor_role,
        "action": event.action,
        "outcome": event.outcome,
        "target_type": event.target_type,
        "target_id": event.target_id,
        "ip_address": event.ip_address,
        "user_agent": event.user_agent,
        "request_id": event.request_id,
        "details": event.details or {},
    }


async def list_events(
    db: AsyncSession,
    *,
    organization_id: Optional[UUID],
    all_organizations: bool = False,
    action: Optional[str] = None,
    actor_user_id: Optional[UUID] = None,
    outcome: Optional[str] = None,
    since: Optional[datetime] = None,
    until: Optional[datetime] = None,
    limit: int = 50,
    cursor: Optional[str] = None,
) -> tuple[list[dict[str, Any]], Optional[str]]:
    """Newest first, keyset-paginated. Org admins always pass their own org."""
    conditions = []
    if not all_organizations:
        conditions.append(AuditEvent.organization_id == organization_id)
    if action:
        # "user." matches every user event; an exact name matches one action.
        conditions.append(AuditEvent.action.startswith(action) if action.endswith(".")
                          else AuditEvent.action == action)
    if actor_user_id:
        conditions.append(AuditEvent.actor_user_id == actor_user_id)
    if outcome:
        conditions.append(AuditEvent.outcome == outcome)
    if since:
        conditions.append(AuditEvent.created_at >= since)
    if until:
        conditions.append(AuditEvent.created_at < until)
    if cursor:
        try:
            at, eid = json.loads(base64.urlsafe_b64decode(cursor.encode()))
            conditions.append(tuple_(AuditEvent.created_at, AuditEvent.id)
                              < tuple_(datetime.fromisoformat(at), UUID(eid)))
        except Exception as exc:
            raise ValueError("Invalid cursor") from exc
    rows = (await db.execute(
        select(AuditEvent).where(and_(*conditions))
        .order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc())
        .limit(limit + 1)
    )).scalars().all()
    page = rows[:limit]
    next_cursor = None
    if len(rows) > limit and page:
        last = page[-1]
        next_cursor = base64.urlsafe_b64encode(
            json.dumps([last.created_at.isoformat(), str(last.id)]).encode()
        ).decode()
    return [event_dict(e) for e in page], next_cursor


async def purge_expired(db: AsyncSession, *, older_than: timedelta) -> int:
    cutoff = datetime.now(timezone.utc) - older_than
    result = await db.execute(delete(AuditEvent).where(AuditEvent.created_at < cutoff))
    await db.commit()
    return result.rowcount
