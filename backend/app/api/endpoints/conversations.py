"""Chat history API: list, search, read, rename, pin, archive, delete, restore.

Every route is scoped to the caller's organization AND user. Conversations of
other users or tenants are indistinguishable from missing ones (404).
"""
from __future__ import annotations

from datetime import timedelta
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from loguru import logger
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth import get_current_user
from app.core.config import settings
from app.db.session import get_db
from app.models.conversation import TITLE_MAX_LENGTH
from app.models.user import User
from app.services.generation.context_manager import context_manager
from app.services.generation.conversation_manager import (
    HIGHLIGHT_END,
    HIGHLIGHT_START,
    conversation_store,
    message_dict,
    summary,
)

router = APIRouter()

MAX_BULK = 100


class ConversationUpdate(BaseModel):
    title: Optional[str] = Field(default=None, max_length=TITLE_MAX_LENGTH)
    is_pinned: Optional[bool] = None
    is_archived: Optional[bool] = None

    @model_validator(mode="after")
    def at_least_one(self) -> "ConversationUpdate":
        if self.title is None and self.is_pinned is None and self.is_archived is None:
            raise ValueError("Provide title, is_pinned or is_archived")
        return self


class BulkIds(BaseModel):
    ids: list[UUID] = Field(min_length=1, max_length=MAX_BULK)


def _tenant(user: User) -> UUID:
    if not user.organization_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "User is not assigned to an organization")
    return user.organization_id


async def _owned(db: AsyncSession, conversation_id: UUID, user: User, *, include_deleted=False):
    conversation = await conversation_store.get_owned(
        db, conversation_id, organization_id=_tenant(user), user_id=user.id,
        include_deleted=include_deleted,
    )
    if conversation is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found")
    return conversation


def _restorable_until(conversation) -> Optional[str]:
    if conversation.deleted_at is None:
        return None
    return (conversation.deleted_at + timedelta(days=settings.conversation_delete_retention_days)).isoformat()


async def load_conversation_dict(
    db: AsyncSession, conversation_id: UUID, user: User, *, message_limit: int = 10_000
) -> dict[str, Any]:
    """Full conversation for exports/analytics; raises 404 when not owned."""
    conversation = await _owned(db, conversation_id, user)
    messages, _ = await conversation_store.messages(db, conversation, limit=message_limit)
    return {
        **summary(conversation),
        "user_id": str(conversation.user_id),
        "metadata": conversation.conversation_metadata or {},
        "context": conversation.context or {},
        "messages": [message_dict(m) for m in messages],
    }


@router.get("/chat/conversations")
async def list_conversations(
    limit: int = Query(30, ge=1, le=100),
    cursor: Optional[str] = Query(None, max_length=500),
    q: Optional[str] = Query(None, max_length=200, description="Search titles and messages"),
    archived: bool = Query(False),
    pinned: bool = Query(False, description="Only pinned conversations"),
    deleted: bool = Query(False, description="Recently deleted (restorable) conversations"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Pinned first, then most recent. Use ``next_cursor`` for the next page.

    Search snippets mark matches with U+0002 (start) and U+0003 (end).
    """
    try:
        items, next_cursor = await conversation_store.list(
            db, organization_id=_tenant(user), user_id=user.id, limit=limit, cursor=cursor,
            q=q, archived=archived, pinned_only=pinned, deleted=deleted,
        )
    except ValueError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid cursor")
    return {
        "items": items,
        "next_cursor": next_cursor,
        "highlight": {"start": HIGHLIGHT_START, "end": HIGHLIGHT_END},
        "retention_days": settings.conversation_delete_retention_days,
    }


@router.get("/chat/conversations/stats")
async def conversation_stats(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return await conversation_store.owner_stats(db, organization_id=_tenant(user), user_id=user.id)


@router.post("/chat/conversations/bulk-delete")
async def bulk_delete(
    body: BulkIds,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Soft-delete many; ids the caller does not own are silently ignored."""
    deleted = await conversation_store.soft_delete(
        db, organization_id=_tenant(user), user_id=user.id, conversation_ids=body.ids
    )
    for conversation_id in body.ids:
        await context_manager.delete_context(str(conversation_id))
    logger.info(f"User {user.id} deleted {deleted} conversations")
    return {"deleted": deleted, "retention_days": settings.conversation_delete_retention_days}


@router.get("/chat/conversations/{conversation_id}")
async def get_conversation(
    conversation_id: UUID,
    limit: int = Query(200, ge=1, le=1000),
    before: Optional[int] = Query(None, ge=1, description="Load messages older than this sequence"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    conversation = await _owned(db, conversation_id, user)
    messages, has_more = await conversation_store.messages(
        db, conversation, limit=limit, before_sequence=before
    )
    return {
        **summary(conversation),
        "user_id": str(conversation.user_id),
        "metadata": conversation.conversation_metadata or {},
        "context": conversation.context or {},
        "messages": [message_dict(m) for m in messages],
        "has_more_before": has_more,
    }


@router.patch("/chat/conversations/{conversation_id}")
async def update_conversation(
    conversation_id: UUID,
    body: ConversationUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    conversation = await _owned(db, conversation_id, user)
    if body.title is not None:
        try:
            await conversation_store.rename(db, conversation, body.title)
        except ValueError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))
    if body.is_archived is not None:
        await conversation_store.set_archived(db, conversation, body.is_archived)
    if body.is_pinned is not None:
        if body.is_pinned and conversation.is_archived:
            raise HTTPException(status.HTTP_409_CONFLICT, "Unarchive the conversation before pinning it")
        await conversation_store.set_pinned(db, conversation, body.is_pinned)
    return summary(conversation)


@router.delete("/chat/conversations/{conversation_id}")
async def delete_conversation(
    conversation_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Soft delete: restorable until the retention window ends."""
    await _owned(db, conversation_id, user)
    await conversation_store.soft_delete(
        db, organization_id=_tenant(user), user_id=user.id, conversation_ids=[conversation_id]
    )
    await context_manager.delete_context(str(conversation_id))
    conversation = await _owned(db, conversation_id, user, include_deleted=True)
    return {
        "message": "Conversation deleted",
        "conversation_id": str(conversation_id),
        "restorable_until": _restorable_until(conversation),
    }


@router.post("/chat/conversations/{conversation_id}/restore")
async def restore_conversation(
    conversation_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    conversation = await _owned(db, conversation_id, user, include_deleted=True)
    if conversation.deleted_at is None:
        return summary(conversation)
    await conversation_store.restore(db, conversation)
    return summary(conversation)


@router.delete("/chat/conversations/{conversation_id}/permanent")
async def delete_conversation_permanently(
    conversation_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Irreversible. Only allowed from the deleted list, so it is always a deliberate second step."""
    conversation = await _owned(db, conversation_id, user, include_deleted=True)
    if conversation.deleted_at is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Delete the conversation first")
    await db.delete(conversation)
    await db.commit()
    logger.info(f"User {user.id} permanently deleted conversation {conversation_id}")
    return {"message": "Conversation permanently deleted", "conversation_id": str(conversation_id)}
