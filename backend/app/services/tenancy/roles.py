"""Who may grant which role.

Rules, enforced in one place for create, update and invitations:
  * nobody but a super admin can grant or revoke ``super_admin``;
  * only super admins can grant or revoke ``org_admin``;
  * org admins (``admin``/``org_admin``) manage ``user`` and ``admin`` roles,
    only inside their own organization, and cannot change their own role;
  * an organization must always keep at least one active admin.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User

ROLES = ("user", "admin", "org_admin", "super_admin")
ORG_ADMIN_ROLES = ("admin", "org_admin")


class RoleChangeDenied(PermissionError):
    pass


def assert_can_grant(actor: User, new_role: str, target: Optional[User] = None) -> None:
    if new_role not in ROLES:
        raise RoleChangeDenied(f"Unknown role: {new_role}")
    if actor.is_super_admin():
        return
    if new_role in ("super_admin", "org_admin"):
        raise RoleChangeDenied(f"Only super admins can grant the {new_role} role")
    if target is not None:
        if target.role in ("super_admin", "org_admin"):
            raise RoleChangeDenied(f"Only super admins can change a {target.role}")
        if target.organization_id != actor.organization_id:
            raise RoleChangeDenied("You can only manage users in your organization")
        if target.id == actor.id and new_role != actor.role:
            raise RoleChangeDenied("You cannot change your own role")


async def assert_keeps_an_admin(db: AsyncSession, target: User, *, new_role: Optional[str] = None,
                                deactivating: bool = False, deleting: bool = False) -> None:
    """Refuse a change that would leave the organization without an active admin."""
    if target.organization_id is None or target.role not in ORG_ADMIN_ROLES or not target.is_active:
        return
    losing_admin = deleting or deactivating or (new_role is not None and new_role not in ORG_ADMIN_ROLES)
    if not losing_admin:
        return
    others = (await db.execute(
        select(func.count()).select_from(User).where(
            User.organization_id == target.organization_id,
            User.role.in_(ORG_ADMIN_ROLES),
            User.is_active.is_(True),
            User.id != target.id,
        )
    )).scalar_one()
    if others == 0:
        raise RoleChangeDenied("The organization must keep at least one active admin")
