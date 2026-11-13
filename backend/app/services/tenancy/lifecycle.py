"""Organization lifecycle: active ⇄ suspended → deleted.

Suspension is reversible and keeps all data; every member is locked out at
the auth layer immediately. Deletion is permanent, only allowed for a
suspended organization, and removes every row and every stored file.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from loguru import logger
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

from app.models.document import Chunk, Document
from app.models.organization import Organization
from app.models.user import RefreshToken, User
from app.services.tenancy import audit
from app.services.tenancy.audit import Action


class LifecycleError(ValueError):
    pass


def _invalidate_caches(organization_id: Any) -> None:
    from app.services.ai import registry
    from app.services.tenancy import limits

    registry.invalidate_tenant(organization_id)
    limits.invalidate(organization_id)


async def suspend(db: AsyncSession, org: Organization, *, actor: User, reason: str,
                  request: Optional[Request] = None) -> Organization:
    if not org.is_active:
        raise LifecycleError("Organization is already suspended")
    org.is_active = False
    org.suspended_at = datetime.now(timezone.utc)
    org.suspended_reason = reason
    org.updated_at = org.suspended_at
    # Refresh tokens are re-checked anyway; revoking them makes the lockout
    # survive a later reactivation of a compromised tenant.
    member_ids = select(User.id).where(User.organization_id == org.id)
    await db.execute(update(RefreshToken).where(RefreshToken.user_id.in_(member_ids)).values(revoked=True))
    audit.record(db, Action.ORG_SUSPENDED, actor=actor, organization_id=org.id,
                 target_type="organization", target_id=org.id, details={"reason": reason},
                 request=request)
    await db.commit()
    _invalidate_caches(org.id)
    logger.warning(f"Organization {org.id} suspended by {actor.id}")
    return org


async def reactivate(db: AsyncSession, org: Organization, *, actor: User,
                     request: Optional[Request] = None) -> Organization:
    if org.is_active:
        raise LifecycleError("Organization is already active")
    previous_reason = org.suspended_reason
    org.is_active = True
    org.suspended_at = None
    org.suspended_reason = None
    org.updated_at = datetime.now(timezone.utc)
    audit.record(db, Action.ORG_REACTIVATED, actor=actor, organization_id=org.id,
                 target_type="organization", target_id=org.id,
                 details={"previous_reason": previous_reason}, request=request)
    await db.commit()
    _invalidate_caches(org.id)
    return org


async def delete_permanently(db: AsyncSession, org: Organization, *, actor: User, confirm_name: str,
                             request: Optional[Request] = None) -> dict[str, int]:
    """Remove the organization, its users, documents, chunks, conversations and files."""
    if org.is_active:
        raise LifecycleError("Suspend the organization before deleting it")
    if confirm_name != org.name:
        raise LifecycleError("Confirmation does not match the organization name")

    documents = (await db.execute(
        select(Document.id, Document.file_path).where(Document.organization_id == org.id)
    )).all()
    doc_ids = [doc_id for doc_id, _ in documents]
    file_paths = [Path(path) for _, path in documents if path]
    member_ids = [uid for (uid,) in (await db.execute(
        select(User.id).where(User.organization_id == org.id)
    )).all()]

    # Bulk deletes in dependency order; conversations, invitations,
    # customization and the org's own audit rows cascade from organizations.
    if doc_ids:
        await db.execute(delete(Chunk).where(Chunk.document_id.in_(doc_ids)))
        await db.execute(delete(Document).where(Document.id.in_(doc_ids)))
    if member_ids:
        await db.execute(delete(RefreshToken).where(RefreshToken.user_id.in_(member_ids)))
        await db.execute(delete(User).where(User.id.in_(member_ids)))
    org_id, org_name = org.id, org.name
    await db.delete(org)
    # Recorded as a platform event: the org's own audit rows go with it.
    audit.record(db, Action.ORG_DELETED, actor=actor, organization_id=None,
                 target_type="organization", target_id=org_id,
                 details={"name": org_name, "users": len(member_ids), "documents": len(doc_ids)},
                 request=request)
    await db.commit()
    _invalidate_caches(org_id)

    removed_files = 0
    for path in file_paths:
        try:
            if path.exists():
                path.unlink()
                removed_files += 1
            if path.parent.exists() and not any(path.parent.iterdir()):
                path.parent.rmdir()
        except OSError as exc:
            logger.error(f"Could not remove {path.name} of deleted org {org_id}: {type(exc).__name__}")
    logger.warning(f"Organization {org_id} permanently deleted by {actor.id}")
    return {"users": len(member_ids), "documents": len(doc_ids), "files_removed": removed_files}
