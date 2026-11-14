""" Admin API endpoints for user and system management, Only accessible by users with admin role """

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from loguru import logger
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth import get_current_admin_user
from app.core.security import get_password_hash, validate_email, validate_password_strength
from app.db.session import get_db
from app.models.document import Document
from app.models.organization import Organization
from app.models.user import RefreshToken, User
from app.services.tenancy import audit
from app.services.tenancy.audit import Action
from app.services.tenancy.quotas import QuotaExceeded, ensure_user_capacity
from app.services.tenancy.roles import RoleChangeDenied, assert_can_grant, assert_keeps_an_admin

router = APIRouter()


# Request / Response Models                         ─

class CreateUserRequest(BaseModel):
    email: EmailStr
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=8)
    full_name: Optional[str] = None
    role: str = Field(default="user", pattern="^(user|admin|org_admin)$")
    is_active: bool = True


class UpdateUserRequest(BaseModel):
    full_name: Optional[str] = None
    # FIX: broadened to include org_admin and super_admin — role escalation
    # is blocked at the endpoint level, not via Pydantic pattern alone
    role: Optional[str] = Field(
        None,
        pattern="^(user|admin|org_admin|super_admin)$",
    )
    is_active: Optional[bool] = None
    is_verified: Optional[bool] = None


class UserListItem(BaseModel):
    id: str
    email: str
    username: str
    full_name: Optional[str]
    role: str
    is_active: bool
    is_verified: bool
    created_at: str
    last_login: Optional[str]
    document_count: int = 0


class UserStatsResponse(BaseModel):
    total_users: int
    active_users: int
    admin_users: int
    regular_users: int
    verified_users: int


class SystemStatsResponse(BaseModel):
    total_users: int
    total_documents: int
    total_chunks: int
    active_sessions: int
    storage_used_mb: float


# User Management                              ─

@router.get("/admin/users", response_model=dict)
async def list_users(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    role: Optional[str] = Query(None),
    is_active: Optional[bool] = Query(None),
    search: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin_user),
):
    """List users scoped to the admin's organization (global for super admins)."""
    query = select(User)

    if admin.is_org_admin() and not admin.is_super_admin():
        query = query.where(User.organization_id == admin.organization_id)

    if role:
        query = query.where(User.role == role)
    if is_active is not None:
        query = query.where(User.is_active == is_active)
    if search:
        pat = f"%{search}%"
        query = query.where(
            User.email.ilike(pat) | User.username.ilike(pat) | User.full_name.ilike(pat)
        )

    total = (await db.execute(select(func.count()).select_from(query.subquery()))).scalar()

    query = query.order_by(User.created_at.desc()).offset(skip).limit(limit)
    users = (await db.execute(query)).scalars().all()

    # One grouped query instead of one count per listed user.
    doc_counts: dict = {}
    if users:
        doc_counts = dict((await db.execute(
            select(Document.uploaded_by, func.count())
            .where(Document.uploaded_by.in_([u.id for u in users]))
            .group_by(Document.uploaded_by)
        )).all())

    user_list = []
    for user in users:
        doc_count = doc_counts.get(user.id, 0)
        user_list.append(
            UserListItem(
                id=str(user.id),
                email=user.email,
                username=user.username,
                full_name=user.full_name,
                role=user.role,
                is_active=user.is_active,
                is_verified=user.is_verified,
                created_at=user.created_at.isoformat(),
                last_login=user.last_login.isoformat() if user.last_login else None,
                document_count=doc_count,
            )
        )

    return {"total": total, "users": user_list}


@router.get("/admin/users/stats", response_model=UserStatsResponse)
async def get_user_stats(
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin_user),
):
    """User statistics, org-scoped for org admins."""
    base = select(func.count()).select_from(User)

    def _org_filter(q):
        if admin.is_org_admin() and not admin.is_super_admin():
            return q.where(User.organization_id == admin.organization_id)
        return q

    total = (await db.execute(_org_filter(base))).scalar()
    active = (await db.execute(_org_filter(base.where(User.is_active == True)))).scalar()
    admins = (await db.execute(_org_filter(base.where(User.role.in_(["org_admin", "super_admin", "admin"]))))).scalar()
    verified = (await db.execute(_org_filter(base.where(User.is_verified == True)))).scalar()

    return UserStatsResponse(
        total_users=total,
        active_users=active,
        admin_users=admins,
        regular_users=total - admins,
        verified_users=verified,
    )


async def _managed_user(db: AsyncSession, admin: User, user_id: UUID) -> User:
    """Load a user the admin may manage.

    Org admins only see their own organization, and nobody below super admin
    can manage a super admin. Out-of-scope users are reported as missing so
    the endpoint is not an existence oracle across tenants.
    """
    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    if not admin.is_super_admin():
        if user.organization_id != admin.organization_id or user.role == "super_admin":
            raise HTTPException(status_code=404, detail="User not found")
    return user


def _quota_error(exc: QuotaExceeded) -> HTTPException:
    return HTTPException(status_code=403, detail=exc.as_detail())


@router.post("/admin/users", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_user(
    request: CreateUserRequest,
    http_request: Request,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin_user),
):
    if not validate_email(request.email):
        raise HTTPException(status_code=400, detail="Invalid email format")

    is_valid, error_msg = validate_password_strength(request.password)
    if not is_valid:
        raise HTTPException(status_code=400, detail=error_msg)
    try:
        assert_can_grant(admin, request.role)
    except RoleChangeDenied as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    if not admin.organization_id:
        raise HTTPException(status_code=400, detail="Create users from within an organization")

    if (await db.execute(select(User).where(func.lower(User.email) == request.email.lower()))).scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already registered")
    if (await db.execute(select(User).where(User.username == request.username))).scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Username already taken")

    if request.is_active:
        try:
            await ensure_user_capacity(db, admin.organization_id)
        except QuotaExceeded as exc:
            actor = audit.snapshot(admin)
            await db.rollback()  # release the organization row lock first
            await audit.record_independent(Action.QUOTA_EXCEEDED, actor=actor, outcome="denied",
                                           details=exc.as_detail(), request=http_request)
            raise _quota_error(exc)

    new_user = User(
        email=request.email.lower(),
        username=request.username,
        hashed_password=get_password_hash(request.password),
        full_name=request.full_name,
        role=request.role,
        is_active=request.is_active,
        is_verified=True,
        organization_id=admin.organization_id,
        user_metadata={"created_by": str(admin.id), "created_by_admin": True},
    )
    db.add(new_user)
    await db.flush()
    audit.record(db, Action.USER_CREATED, actor=admin, target_type="user", target_id=new_user.id,
                 details={"email": new_user.email, "role": new_user.role}, request=http_request)
    await db.commit()
    await db.refresh(new_user)

    logger.info(f"Admin {admin.id} created user {new_user.id} in org {admin.organization_id}")
    return {"message": "User created successfully", "user": new_user.to_dict()}


@router.get("/admin/users/{user_id}", response_model=dict)
async def get_user_details(
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin_user),
):
    user = await _managed_user(db, admin, user_id)

    doc_count = (
        await db.execute(
            select(func.count()).select_from(Document).where(Document.uploaded_by == user_id)
        )
    ).scalar()

    recent_docs = (
        await db.execute(
            select(Document).where(Document.uploaded_by == user_id)
            .order_by(Document.upload_date.desc()).limit(5)
        )
    ).scalars().all()

    return {
        "user": user.to_dict(),
        "stats": {"total_documents": doc_count},
        "recent_documents": [
            {
                "id": str(doc.id),
                "filename": doc.filename,
                "upload_date": doc.upload_date.isoformat(),
                "status": doc.status,
            }
            for doc in recent_docs
        ],
    }


@router.put("/admin/users/{user_id}", response_model=dict)
async def update_user(
    user_id: UUID,
    request: UpdateUserRequest,
    http_request: Request,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin_user),
):
    user = await _managed_user(db, admin, user_id)
    try:
        if request.role is not None and request.role != user.role:
            # Previously super_admin could be granted by any org admin.
            assert_can_grant(admin, request.role, target=user)
            await assert_keeps_an_admin(db, user, new_role=request.role)
        if request.is_active is False and user.is_active:
            if user_id == admin.id:
                raise RoleChangeDenied("You cannot deactivate your own account")
            await assert_keeps_an_admin(db, user, deactivating=True)
    except RoleChangeDenied as exc:
        raise HTTPException(status_code=403, detail=str(exc))

    if request.is_active and not user.is_active and user.organization_id:
        try:
            await ensure_user_capacity(db, user.organization_id)
        except QuotaExceeded as exc:
            actor = audit.snapshot(admin)
            await db.rollback()  # release the organization row lock first
            await audit.record_independent(Action.QUOTA_EXCEEDED, actor=actor, outcome="denied",
                                           details=exc.as_detail(), request=http_request)
            raise _quota_error(exc)

    changes: dict = {}
    if request.full_name is not None and request.full_name != user.full_name:
        changes["full_name"] = True
        user.full_name = request.full_name
    if request.role is not None and request.role != user.role:
        audit.record(db, Action.USER_ROLE_CHANGED, actor=admin, organization_id=user.organization_id,
                     target_type="user", target_id=user.id,
                     details={"from": user.role, "to": request.role}, request=http_request)
        user.role = request.role
    if request.is_active is not None and request.is_active != user.is_active:
        user.is_active = request.is_active
        if not request.is_active:
            # End every session now; access tokens are re-checked per request.
            await db.execute(update(RefreshToken).where(RefreshToken.user_id == user.id)
                             .values(revoked=True))
        audit.record(db, Action.USER_REACTIVATED if request.is_active else Action.USER_DEACTIVATED,
                     actor=admin, organization_id=user.organization_id, target_type="user",
                     target_id=user.id, request=http_request)
    if request.is_verified is not None and request.is_verified != user.is_verified:
        changes["is_verified"] = request.is_verified
        user.is_verified = request.is_verified
    if changes:
        audit.record(db, Action.USER_UPDATED, actor=admin, organization_id=user.organization_id,
                     target_type="user", target_id=user.id, details=changes, request=http_request)

    user.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(user)

    logger.info(f"Admin {admin.id} updated user {user.id}")
    return {"message": "User updated successfully", "user": user.to_dict()}


@router.delete("/admin/users/{user_id}")
async def delete_user(
    user_id: UUID,
    http_request: Request,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin_user),
):
    user = await _managed_user(db, admin, user_id)
    if user_id == admin.id:
        raise HTTPException(status_code=400, detail="Cannot delete your own account")
    try:
        await assert_keeps_an_admin(db, user, deleting=True)
    except RoleChangeDenied as exc:
        raise HTTPException(status_code=403, detail=str(exc))

    # Documents belong to the organization, not the uploader: uploaded_by is
    # set to NULL by the foreign key. (Deleting them here used to wipe part of
    # the knowledge base and orphan the files on disk.)
    audit.record(db, Action.USER_DELETED, actor=admin, organization_id=user.organization_id,
                 target_type="user", target_id=user.id, details={"email": user.email},
                 request=http_request)
    await db.execute(delete(RefreshToken).where(RefreshToken.user_id == user.id))
    await db.delete(user)
    await db.commit()

    logger.info(f"Admin {admin.id} deleted user {user_id}")
    return {"message": "User deleted successfully", "user_id": str(user_id)}


class AdminPasswordReset(BaseModel):
    new_password: str = Field(..., min_length=8, max_length=128)


@router.post("/admin/users/{user_id}/reset-password")
async def reset_user_password(
    user_id: UUID,
    http_request: Request,
    body: Optional[AdminPasswordReset] = None,
    new_password: Optional[str] = Query(None, min_length=8, deprecated=True,
                                        description="Deprecated: send it in the JSON body"),
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin_user),
):
    """Set a user's password. Scoped like every other user action.

    This endpoint had no organization or role check, so any org admin could
    take over any account on the platform. The password now travels in the
    body; query strings end up in access logs.
    """
    password = body.new_password if body else new_password
    if not password:
        raise HTTPException(status_code=422, detail="new_password is required")
    user = await _managed_user(db, admin, user_id)
    if user.role in ("org_admin",) and not admin.is_super_admin() and user.id != admin.id:
        raise HTTPException(status_code=403, detail="Only super admins can reset an organization admin's password")
    is_valid, error_msg = validate_password_strength(password)
    if not is_valid:
        raise HTTPException(status_code=400, detail=error_msg)

    user.hashed_password = get_password_hash(password)
    user.updated_at = datetime.now(timezone.utc)
    # Old sessions must not survive a password reset.
    await db.execute(update(RefreshToken).where(RefreshToken.user_id == user.id).values(revoked=True))
    audit.record(db, Action.USER_PASSWORD_RESET_BY_ADMIN, actor=admin,
                 organization_id=user.organization_id, target_type="user", target_id=user.id,
                 request=http_request)
    await db.commit()
    logger.info(f"Admin {admin.id} reset password for user {user.id}")
    return {"message": "Password reset successfully"}


# System Stats

@router.get("/admin/stats/system", response_model=SystemStatsResponse)
async def get_system_stats(
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin_user),
):
    """System-wide statistics, org-scoped for org admins."""

    def _ou(q):
        if admin.is_org_admin() and not admin.is_super_admin():
            return q.where(User.organization_id == admin.organization_id)
        return q

    def _od(q):
        if admin.is_org_admin() and not admin.is_super_admin():
            return q.where(Document.organization_id == admin.organization_id)
        return q

    total_users = (await db.execute(_ou(select(func.count()).select_from(User)))).scalar()
    total_docs = (await db.execute(_od(select(func.count()).select_from(Document)))).scalar()
    storage_bytes = (
        await db.execute(_od(select(func.sum(Document.file_size_bytes)).select_from(Document)))
    ).scalar() or 0

    from app.models.document import Chunk
    chunk_q = select(func.count()).select_from(Chunk)
    if admin.is_org_admin() and not admin.is_super_admin():
        chunk_q = chunk_q.join(Document).where(Document.organization_id == admin.organization_id)
    total_chunks = (await db.execute(chunk_q)).scalar()

    return SystemStatsResponse(
        total_users=total_users,
        total_documents=total_docs,
        total_chunks=total_chunks,
        active_sessions=0,
        storage_used_mb=round(storage_bytes / (1024 * 1024), 2),
    )


@router.get("/admin/documents", response_model=dict)
async def list_all_documents(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    doc_type: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    user_id: Optional[UUID] = Query(None),
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin_user),
):
    query = select(Document)
    if admin.is_org_admin() and not admin.is_super_admin():
        query = query.where(Document.organization_id == admin.organization_id)
    if doc_type:
        query = query.where(Document.doc_type == doc_type)
    if status:
        query = query.where(Document.status == status)
    if user_id:
        query = query.where(Document.uploaded_by == user_id)

    total = (await db.execute(select(func.count()).select_from(query.subquery()))).scalar()
    query = query.order_by(Document.upload_date.desc()).offset(skip).limit(limit)
    documents = (await db.execute(query)).scalars().all()

    doc_list = []
    for doc in documents:
        user = (await db.execute(select(User).where(User.id == doc.uploaded_by))).scalar_one_or_none()
        doc_list.append({
            "id": str(doc.id),
            "filename": doc.filename,
            "doc_type": doc.doc_type,
            "department": doc.department,
            "total_pages": doc.total_pages or 0,
            "total_chunks": doc.total_chunks or 0,
            "status": doc.status,
            "upload_date": doc.upload_date.isoformat(),
            "processed_date": doc.processed_date.isoformat() if doc.processed_date else None,
            "uploaded_by": {
                "id": str(user.id),
                "email": user.email,
                "username": user.username,
            } if user else None,
        })

    return {"total": total, "documents": doc_list}


# Analytics                                 ─

@router.get("/admin/analytics/context")
async def get_context_analytics(
    days: int = Query(7, ge=1, le=90),
    current_user: User = Depends(get_current_admin_user),
):
    """
    Context usage analytics.

    FIX: no longer reads context_manager.contexts dict directly (always empty
    in multi-worker deployments). Returns structural metadata only; deep
    per-context stats require a dedicated metrics table (TODO).
    """
    from app.services.generation.context_manager import context_manager

    return {
        "note": (
            "Deep per-conversation analytics require a metrics table. "
            "This endpoint returns service-level config only."
        ),
        "context_features": {
            "query_reformulation": True,
            "document_scoping": True,
            "time_period_tracking": True,
            "entity_extraction": True,
        },
        "config": {
            "context_timeout_hours": getattr(context_manager, "timeout_hours", 1),
            "max_documents": getattr(context_manager, "max_documents", 5),
            "boost_factor": getattr(context_manager, "boost_factor", 1.5),
        },
    }


@router.get("/admin/analytics/retrieval")
async def get_retrieval_analytics(
    current_user: User = Depends(get_current_admin_user),
):
    """Retrieval performance analytics.

    Not implemented: there is no persisted metrics store yet. This endpoint
    previously returned hardcoded placeholder numbers (e.g. p95=300ms) that
    looked like real measurements. Use RAG traces / evaluation reports.
    """
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Retrieval analytics require a metrics store; see evaluation reports.",
    )


def _admin_scope(user: User) -> UUID:
    if not user.organization_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Admin is not assigned to an organization")
    return user.organization_id


@router.get("/admin/conversations/quality")
async def get_conversation_quality_metrics(
    days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
):
    """Answer quality across the admin's organization.

    Aggregates only: admins see rates and conversation ids, never other
    users' message content.
    """
    from datetime import timedelta

    from sqlalchemy import and_, case

    from app.models.conversation import Conversation, ConversationMessage

    since = datetime.now(timezone.utc) - timedelta(days=days)
    meta = ConversationMessage.message_metadata
    finish = meta["finish_reason"].astext
    scope = and_(
        ConversationMessage.organization_id == _admin_scope(current_user),
        ConversationMessage.role == "assistant",
        ConversationMessage.created_at >= since,
    )
    row = (await db.execute(
        select(
            func.count(),
            func.count().filter(meta["confidence"].astext == "low"),
            func.count().filter(and_(
                meta["searched_documents"].astext == "true",
                func.jsonb_array_length(func.coalesce(meta["sources"], text_json_array())) == 0,
            )),
            func.count().filter(finish.in_(["provider_unavailable", "error"])),
            func.count().filter(finish.in_(["insufficient_context", "output_guardrail_rejected", "blocked"])),
            func.count(func.distinct(ConversationMessage.conversation_id)),
        ).where(scope)
    )).one()
    total, low_conf, no_sources, errors, abstained, conversations = row

    issues = (await db.execute(
        select(
            ConversationMessage.conversation_id,
            ConversationMessage.created_at,
            case(
                (finish.in_(["provider_unavailable", "error"]), "error"),
                (meta["confidence"].astext == "low", "low_confidence"),
                else_="abstained",
            ),
        )
        .join(Conversation, Conversation.id == ConversationMessage.conversation_id)
        .where(scope, Conversation.deleted_at.is_(None), or_(
            finish.in_(["provider_unavailable", "error", "insufficient_context",
                        "output_guardrail_rejected", "blocked"]),
            meta["confidence"].astext == "low",
        ))
        .order_by(ConversationMessage.created_at.desc())
        .limit(20)
    )).all()

    def rate(count: int) -> float:
        return round(count / max(total, 1) * 100, 1)

    return {
        "period_days": days,
        "total_conversations_analyzed": conversations,
        "total_responses": total,
        "quality_metrics": {
            "low_confidence_responses": low_conf,
            "low_confidence_rate": rate(low_conf),
            "responses_without_sources": no_sources,
            "no_sources_rate": rate(no_sources),
            "abstained_responses": abstained,
            "abstention_rate": rate(abstained),
            "error_responses": errors,
            "error_rate": rate(errors),
        },
        "quality_issues": [
            {"conversation_id": str(cid), "issue": issue, "timestamp": at.isoformat()}
            for cid, at, issue in issues
        ],
        "recommendations": _generate_quality_recommendations(low_conf, no_sources, errors),
        "health_status": _calculate_health_status(rate(low_conf), rate(errors)),
    }


@router.get("/admin/analytics/conversations")
async def get_conversation_analytics(
    days: int = Query(7, ge=1, le=90),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
):
    """Organization-wide usage over the last ``days`` (aggregates only)."""
    from datetime import timedelta

    from app.models.conversation import Conversation, ConversationMessage

    org_id = _admin_scope(current_user)
    now = datetime.now(timezone.utc)
    since = now - timedelta(days=days)

    conv_row = (await db.execute(
        select(
            func.count(),
            func.count(func.distinct(Conversation.user_id)),
            func.count().filter(Conversation.last_message_at >= now - timedelta(hours=1)),
        ).where(
            Conversation.organization_id == org_id,
            Conversation.deleted_at.is_(None),
            Conversation.last_message_at >= since,
        )
    )).one()
    total_messages = (await db.execute(
        select(func.count()).where(
            ConversationMessage.organization_id == org_id,
            ConversationMessage.created_at >= since,
        )
    )).scalar_one()
    hour = func.extract("hour", ConversationMessage.created_at).label("hour")
    by_hour = (await db.execute(
        select(hour, func.count(func.distinct(ConversationMessage.conversation_id)))
        .where(
            ConversationMessage.organization_id == org_id,
            ConversationMessage.created_at >= since,
            ConversationMessage.role == "user",
        )
        .group_by(hour)
        .order_by(hour)
    )).all()

    total_conversations, active_users, active_last_hour = conv_row
    return {
        "period_days": days,
        "total_conversations": total_conversations,
        "active_users": active_users,
        "total_messages": total_messages,
        "average_conversation_length": round(total_messages / max(total_conversations, 1), 1),
        # Topic extraction was never populated; report nothing rather than fake data.
        "top_topics": [],
        "usage_by_hour": [{"hour": int(h), "conversations": c} for h, c in by_hour],
        "active_conversations": active_last_hour,
    }


def text_json_array():
    from sqlalchemy import literal_column

    return literal_column("'[]'::jsonb")


# Helpers

def _generate_quality_recommendations(
    low_conf: int, no_sources: int, errors: int
) -> list[str]:
    recs = []
    if low_conf > 10:
        recs.append(
            "High number of low-confidence responses. Consider: "
            "1) Improving document quality, 2) Adjusting similarity thresholds, "
            "3) Adding more training documents."
        )
    if no_sources > 20:
        recs.append(
            "Many responses without sources. This may indicate: "
            "1) Too many conversational queries, 2) Documents not covering user questions, "
            "3) Retrieval threshold too high."
        )
    if errors > 5:
        recs.append(
            "Error rate is elevated. Check: 1) API quotas, 2) Database connections, "
            "3) System logs for recurring issues."
        )
    if not recs:
        recs.append("System quality metrics are healthy!")
    return recs


def _calculate_health_status(low_conf_rate: float, error_rate: float) -> str:
    if error_rate > 10 or low_conf_rate > 30:
        return "critical"
    elif error_rate > 5 or low_conf_rate > 20:
        return "warning"
    return "healthy"

__all__ = ["router"]
