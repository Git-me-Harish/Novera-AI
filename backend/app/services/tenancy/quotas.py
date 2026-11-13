"""Organization quotas: seats, documents and storage.

Checks lock the organization row (SELECT ... FOR UPDATE) and must run in the
same transaction as the insert they guard, so two concurrent uploads cannot
both pass a "1 slot left" check. The lock is released by the caller's commit.
A NULL limit means unlimited.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document
from app.models.organization import Organization
from app.models.tenancy import OrganizationInvitation
from app.models.user import User

GB = 1024 ** 3


@dataclass
class QuotaExceeded(Exception):
    resource: str  # users | documents | storage
    limit: int
    current: int
    requested: int

    def __str__(self) -> str:
        noun = {"users": "user seats", "documents": "documents", "storage": "bytes of storage"}[self.resource]
        return f"Organization limit reached: {self.current} of {self.limit} {noun} in use"

    def as_detail(self) -> dict[str, Any]:
        return {
            "code": "quota_exceeded",
            "resource": self.resource,
            "limit": self.limit,
            "current": self.current,
            "requested": self.requested,
            "message": str(self),
        }


async def lock_organization(db: AsyncSession, organization_id: UUID) -> Organization:
    org = (await db.execute(
        select(Organization).where(Organization.id == organization_id).with_for_update()
    )).scalar_one_or_none()
    if org is None:
        raise LookupError("Organization not found")
    return org


async def usage(db: AsyncSession, organization_id: UUID) -> dict[str, int]:
    users = (await db.execute(
        select(func.count()).select_from(User)
        .where(User.organization_id == organization_id, User.is_active.is_(True))
    )).scalar_one()
    pending_invitations = (await db.execute(
        select(func.count()).select_from(OrganizationInvitation).where(
            OrganizationInvitation.organization_id == organization_id,
            OrganizationInvitation.accepted_at.is_(None),
            OrganizationInvitation.revoked_at.is_(None),
            OrganizationInvitation.expires_at > func.now(),
        )
    )).scalar_one()
    documents, storage = (await db.execute(
        select(func.count(), func.coalesce(func.sum(Document.file_size_bytes), 0))
        .where(Document.organization_id == organization_id)
    )).one()
    return {
        "users": users,
        "pending_invitations": pending_invitations,
        "documents": documents,
        "storage_bytes": int(storage),
    }


async def ensure_user_capacity(
    db: AsyncSession, organization_id: UUID, *, additional: int = 1,
    count_pending_invitations: bool = False,
) -> Organization:
    """Lock the org and verify ``additional`` more active users fit.

    Invitations count against seats when creating them, so an admin cannot
    hand out more invites than there are seats; at acceptance time the
    accepted invitation is the one being converted, so it is not counted.
    """
    org = await lock_organization(db, organization_id)
    if org.max_users is not None:
        current = await usage(db, organization_id)
        in_use = current["users"] + (current["pending_invitations"] if count_pending_invitations else 0)
        if in_use + additional > org.max_users:
            raise QuotaExceeded("users", org.max_users, in_use, additional)
    return org


async def ensure_document_capacity(
    db: AsyncSession, organization_id: UUID, *, additional_documents: int = 1,
    additional_bytes: int = 0,
) -> Organization:
    org = await lock_organization(db, organization_id)
    if org.max_documents is None and org.max_storage_gb is None:
        return org
    current = await usage(db, organization_id)
    if org.max_documents is not None and current["documents"] + additional_documents > org.max_documents:
        raise QuotaExceeded("documents", org.max_documents, current["documents"], additional_documents)
    if org.max_storage_gb is not None:
        limit = org.max_storage_gb * GB
        if current["storage_bytes"] + additional_bytes > limit:
            raise QuotaExceeded("storage", limit, current["storage_bytes"], additional_bytes)
    return org


def limits_view(org: Organization, current: Optional[dict] = None) -> dict[str, Any]:
    def entry(limit: Optional[int], used: Optional[int]) -> dict[str, Any]:
        return {
            "limit": limit,
            "used": used,
            "remaining": None if limit is None or used is None else max(limit - used, 0),
            "percent": None if not limit or used is None else round(used / limit * 100, 1),
        }

    current = current or {}
    return {
        "users": entry(org.max_users, current.get("users")),
        "documents": entry(org.max_documents, current.get("documents")),
        "storage_bytes": entry(org.max_storage_gb * GB if org.max_storage_gb else None,
                               current.get("storage_bytes")),
        "pending_invitations": current.get("pending_invitations"),
    }
