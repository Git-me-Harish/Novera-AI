"""Organization membership invitations and the audit log."""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import Column, DateTime, ForeignKey, Index, String, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.db.session import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class OrganizationInvitation(Base):
    """A single-use invitation to join an organization with a given role.

    Only a SHA-256 of the token is stored; the token itself exists only in the
    invitation link, so a database read cannot be turned into account access.
    """

    __tablename__ = "organization_invitations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    organization_id = Column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    email = Column(String(255), nullable=False)
    role = Column(String(20), nullable=False, default="user")
    token_hash = Column(String(64), nullable=False, unique=True)
    invited_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, server_default=func.now())
    expires_at = Column(DateTime(timezone=True), nullable=False)
    accepted_at = Column(DateTime(timezone=True), nullable=True)
    accepted_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    revoked_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        # One open invitation per email per organization.
        Index(
            "uq_org_invitations_open_email",
            "organization_id", func.lower(email),
            unique=True,
            postgresql_where=text("accepted_at IS NULL AND revoked_at IS NULL"),
        ),
        Index("ix_org_invitations_org", "organization_id"),
    )

    @property
    def status(self) -> str:
        if self.accepted_at:
            return "accepted"
        if self.revoked_at:
            return "revoked"
        if self.expires_at <= _utcnow():
            return "expired"
        return "pending"


class AuditEvent(Base):
    """Append-only record of a security-relevant action.

    A database trigger rejects UPDATE; rows leave only through the retention
    purge. ``organization_id`` is null for platform-level events (e.g. a super
    admin creating an organization or a login for an unknown email).
    """

    __tablename__ = "audit_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, server_default=func.now())
    organization_id = Column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True
    )
    actor_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    # Snapshot: the log must stay readable after the user is deleted.
    actor_email = Column(String(255), nullable=True)
    actor_role = Column(String(20), nullable=True)
    action = Column(String(64), nullable=False)
    outcome = Column(String(16), nullable=False, default="success", server_default="success")
    target_type = Column(String(32), nullable=True)
    target_id = Column(String(64), nullable=True)
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(String(255), nullable=True)
    request_id = Column(String(64), nullable=True)
    details = Column(JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb"))

    __table_args__ = (
        Index("ix_audit_events_org_time", "organization_id", "created_at"),
        Index("ix_audit_events_action_time", "action", "created_at"),
        Index("ix_audit_events_actor", "actor_user_id"),
    )
