"""Organization administration: usage and limits, invitations, audit log.

Org admins act on their own organization; super admins may pass
``organization_id`` to act on any organization.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth import get_current_org_admin
from app.db.session import get_db
from app.models.organization import Organization
from app.models.tenancy import OrganizationInvitation
from app.models.user import User
from app.services.tenancy import audit, invitations, quotas
from app.services.tenancy.audit import Action
from app.services.tenancy.limits import effective_limits
from app.services.tenancy.roles import RoleChangeDenied

router = APIRouter()


async def _target_org(db: AsyncSession, user: User, organization_id: Optional[UUID]) -> Organization:
    if user.is_super_admin():
        org_id = organization_id or user.organization_id
    else:
        if organization_id and organization_id != user.organization_id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Cannot manage another organization")
        org_id = user.organization_id
    if not org_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "organization_id is required")
    org = (await db.execute(select(Organization).where(Organization.id == org_id))).scalar_one_or_none()
    if org is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Organization not found")
    return org


# ── usage ────────────────────────────────────────────────────────────────────

@router.get("/organization/usage")
async def organization_usage(
    organization_id: Optional[UUID] = Query(None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_org_admin),
):
    org = await _target_org(db, user, organization_id)
    current = await quotas.usage(db, org.id)
    return {
        "organization_id": str(org.id),
        "status": "active" if org.is_active else "suspended",
        "quotas": quotas.limits_view(org, current),
        "rate_limits": effective_limits(org),
    }


# ── invitations ──────────────────────────────────────────────────────────────

class InvitationCreate(BaseModel):
    email: EmailStr
    role: str = Field("user", pattern="^(user|admin|org_admin)$")


@router.post("/organization/invitations", status_code=status.HTTP_201_CREATED)
async def create_invitation(
    body: InvitationCreate,
    request: Request,
    organization_id: Optional[UUID] = Query(None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_org_admin),
):
    org = await _target_org(db, user, organization_id)
    if not org.is_active:
        raise HTTPException(status.HTTP_409_CONFLICT, "The organization is suspended")
    try:
        invitation, token = await invitations.create(
            db, actor=user, organization_id=org.id, email=body.email, role=body.role
        )
    except RoleChangeDenied as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc))
    except invitations.InvitationError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc))
    except quotas.QuotaExceeded as exc:
        actor, org_id = audit.snapshot(user), org.id
        await db.rollback()  # release the organization row lock first
        await audit.record_independent(Action.QUOTA_EXCEEDED, actor=actor, organization_id=org_id,
                                       outcome="denied", details=exc.as_detail(), request=request)
        raise HTTPException(status.HTTP_403_FORBIDDEN, exc.as_detail())
    audit.record(db, Action.INVITATION_CREATED, actor=user, organization_id=org.id,
                 target_type="invitation", target_id=invitation.id,
                 details={"email": invitation.email, "role": invitation.role}, request=request)
    await db.commit()
    emailed = await invitations.send_email(invitation, token, org.display_name, user.full_name or user.email)
    return {
        **invitations.invitation_dict(invitation),
        "email_sent": emailed,
        # Returned once so the admin can share it when email is not configured.
        # Only its hash is stored; it cannot be retrieved again.
        "invite_url": invitations.invitation_url(token),
    }


@router.get("/organization/invitations")
async def list_invitations(
    status_filter: Optional[str] = Query(None, alias="status", pattern="^(pending|accepted|revoked|expired)$"),
    organization_id: Optional[UUID] = Query(None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_org_admin),
):
    org = await _target_org(db, user, organization_id)
    rows = (await db.execute(
        select(OrganizationInvitation).where(OrganizationInvitation.organization_id == org.id)
        .order_by(OrganizationInvitation.created_at.desc()).limit(500)
    )).scalars().all()
    items = [invitations.invitation_dict(r) for r in rows]
    if status_filter:
        items = [i for i in items if i["status"] == status_filter]
    return {"items": items}


async def _owned_invitation(db, org: Organization, invitation_id: UUID) -> OrganizationInvitation:
    invitation = (await db.execute(select(OrganizationInvitation).where(
        OrganizationInvitation.id == invitation_id,
        OrganizationInvitation.organization_id == org.id,
    ))).scalar_one_or_none()
    if invitation is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Invitation not found")
    return invitation


@router.delete("/organization/invitations/{invitation_id}")
async def revoke_invitation(
    invitation_id: UUID,
    request: Request,
    organization_id: Optional[UUID] = Query(None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_org_admin),
):
    org = await _target_org(db, user, organization_id)
    invitation = await _owned_invitation(db, org, invitation_id)
    if invitation.status != "pending":
        raise HTTPException(status.HTTP_409_CONFLICT, f"Invitation is already {invitation.status}")
    invitation.revoked_at = datetime.now(invitation.expires_at.tzinfo)
    audit.record(db, Action.INVITATION_REVOKED, actor=user, organization_id=org.id,
                 target_type="invitation", target_id=invitation.id,
                 details={"email": invitation.email}, request=request)
    await db.commit()
    return invitations.invitation_dict(invitation)


@router.post("/organization/invitations/{invitation_id}/resend", status_code=status.HTTP_201_CREATED)
async def resend_invitation(
    invitation_id: UUID,
    request: Request,
    organization_id: Optional[UUID] = Query(None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_org_admin),
):
    """Revoke the old link and issue a fresh one (new token, new expiry)."""
    org = await _target_org(db, user, organization_id)
    old = await _owned_invitation(db, org, invitation_id)
    if old.status in ("accepted",):
        raise HTTPException(status.HTTP_409_CONFLICT, "Invitation was already accepted")
    if old.revoked_at is None:
        old.revoked_at = datetime.now(old.expires_at.tzinfo)
        await db.flush()
    return await create_invitation(InvitationCreate(email=old.email, role=old.role), request,
                                   org.id if user.is_super_admin() else None, db, user)


# ── audit log ────────────────────────────────────────────────────────────────

@router.get("/organization/audit-log")
async def organization_audit_log(
    action: Optional[str] = Query(None, max_length=64, description='Exact action or prefix ending in "."'),
    actor_user_id: Optional[UUID] = Query(None),
    outcome: Optional[str] = Query(None, pattern="^(success|failure|denied)$"),
    since: Optional[datetime] = Query(None),
    until: Optional[datetime] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    cursor: Optional[str] = Query(None, max_length=500),
    organization_id: Optional[UUID] = Query(None),
    all_organizations: bool = Query(False, description="Super admins only: every tenant and platform events"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_org_admin),
):
    if all_organizations and not user.is_super_admin():
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Super admin access required")
    org_id = None if all_organizations else (await _target_org(db, user, organization_id)).id
    try:
        items, next_cursor = await audit.list_events(
            db, organization_id=org_id, all_organizations=all_organizations, action=action,
            actor_user_id=actor_user_id, outcome=outcome, since=since, until=until,
            limit=limit, cursor=cursor,
        )
    except ValueError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid cursor")
    return {"items": items, "next_cursor": next_cursor}
