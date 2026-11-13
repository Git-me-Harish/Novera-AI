"""Durable, tenant-scoped conversation store (PostgreSQL).

Replaces the Redis store, which expired every conversation after 2 hours and
silently dropped all but the first and last 29 messages.

Rules every method follows:
  * every read and write is scoped by BOTH organization_id and user_id;
  * appends lock the conversation row, so concurrent sends (double-submit,
    two tabs) get distinct, gap-free sequence numbers;
  * writes commit immediately — chat history must survive a later failure in
    the same request and the streaming path, which runs after FastAPI's
    request-scoped session has already been committed.
"""
from __future__ import annotations

import base64
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Optional, Protocol
from uuid import UUID, uuid4

from loguru import logger
from sqlalchemy import and_, delete, func, or_, select, text, tuple_, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import (
    DEFAULT_TITLE,
    TITLE_MAX_LENGTH,
    Conversation,
    ConversationMessage,
)

PREVIEW_CHARS = 160
# Snippet highlight markers: control characters cannot appear in normalized
# user text, so the client can split on them without HTML injection risk.
HIGHLIGHT_START = "\u0002"
HIGHLIGHT_END = "\u0003"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _uuid(value: Any) -> UUID:
    return value if isinstance(value, UUID) else UUID(str(value))


def title_from_question(question: str) -> str:
    """Deterministic placeholder title: the first question, cut at a word."""
    cleaned = " ".join((question or "").split()).strip()
    if not cleaned:
        return DEFAULT_TITLE
    if len(cleaned) <= 60:
        return cleaned[0].upper() + cleaned[1:]
    cut = cleaned[:60].rsplit(" ", 1)[0] or cleaned[:60]
    return (cut[0].upper() + cut[1:]).rstrip(",;:-") + "…"


def clean_title(raw: str) -> Optional[str]:
    """Normalize a user- or model-supplied title; None if nothing usable remains."""
    line = next((part for part in (raw or "").splitlines() if part.strip()), "")
    line = re.sub(r"^(title\s*:\s*)", "", line.strip(), flags=re.IGNORECASE)
    line = line.strip().strip("#*_`\"'“”‘’ ").rstrip(".")
    line = " ".join(line.split())
    if not line:
        return None
    return line[:TITLE_MAX_LENGTH]


def _search_query(q: str) -> Optional[str]:
    """Safe prefix tsquery: 'leave poli' -> 'leave:* & poli:*'."""
    terms = re.findall(r"\w+", q.lower(), flags=re.UNICODE)[:8]
    return " & ".join(f"{term}:*" for term in terms) if terms else None


def _encode_cursor(conv: Conversation) -> str:
    raw = json.dumps([conv.is_pinned, conv.last_message_at.isoformat(), str(conv.id)])
    return base64.urlsafe_b64encode(raw.encode()).decode()


def _decode_cursor(cursor: str) -> tuple[bool, datetime, UUID]:
    try:
        pinned, at, cid = json.loads(base64.urlsafe_b64decode(cursor.encode()))
        return bool(pinned), datetime.fromisoformat(at), UUID(cid)
    except Exception as exc:
        raise ValueError("Invalid cursor") from exc


def summary(conv: Conversation, *, preview: Optional[str] = None,
            snippet: Optional[str] = None) -> dict[str, Any]:
    return {
        "id": str(conv.id),
        "title": conv.title,
        "title_source": conv.title_source,
        "is_pinned": conv.is_pinned,
        "is_archived": conv.is_archived,
        "message_count": conv.message_count,
        "last_message_at": conv.last_message_at.isoformat(),
        "created_at": conv.created_at.isoformat(),
        "updated_at": conv.updated_at.isoformat(),
        "deleted_at": conv.deleted_at.isoformat() if conv.deleted_at else None,
        "preview": preview,
        "snippet": snippet,
    }


def message_dict(message: ConversationMessage) -> dict[str, Any]:
    return {
        "id": str(message.id),
        "sequence": message.sequence,
        "role": message.role,
        "content": message.content,
        "timestamp": message.created_at.isoformat(),
        "metadata": message.message_metadata or {},
    }


class ConversationStoreProtocol(Protocol):
    """The subset of the store the chat pipeline depends on."""

    async def get_owned(self, db, conversation_id, *, organization_id, user_id,
                        include_deleted: bool = False): ...
    async def create(self, db, *, organization_id, user_id, first_question: str = "",
                     metadata: Optional[dict] = None): ...
    async def append_message(self, db, conversation, role: str, content: str,
                             metadata: Optional[dict] = None): ...
    async def recent_history(self, db, conversation, turns: int) -> list[dict[str, str]]: ...
    async def save_context(self, db, conversation, context: dict) -> None: ...


class ConversationStore:
    """PostgreSQL-backed conversation history."""

    # ── ownership ────────────────────────────────────────────────────────────

    async def get_owned(
        self,
        db: AsyncSession,
        conversation_id: Any,
        *,
        organization_id: Any,
        user_id: Any,
        include_deleted: bool = False,
    ) -> Optional[Conversation]:
        try:
            cid = _uuid(conversation_id)
        except (ValueError, TypeError):
            return None
        conditions = [
            Conversation.id == cid,
            Conversation.organization_id == _uuid(organization_id),
            Conversation.user_id == _uuid(user_id),
        ]
        if not include_deleted:
            conditions.append(Conversation.deleted_at.is_(None))
        return (await db.execute(select(Conversation).where(*conditions))).scalar_one_or_none()

    async def exists_for_other_owner(self, db: AsyncSession, conversation_id: Any) -> bool:
        """True when the id exists but is not visible to the caller (for 404-vs-new decisions)."""
        try:
            cid = _uuid(conversation_id)
        except (ValueError, TypeError):
            return False
        return (await db.execute(
            select(func.count()).select_from(Conversation).where(Conversation.id == cid)
        )).scalar_one() > 0

    # ── writes ───────────────────────────────────────────────────────────────

    async def create(
        self,
        db: AsyncSession,
        *,
        organization_id: Any,
        user_id: Any,
        first_question: str = "",
        metadata: Optional[dict] = None,
    ) -> Conversation:
        now = _utcnow()
        conv = Conversation(
            id=uuid4(),
            organization_id=_uuid(organization_id),
            user_id=_uuid(user_id),
            title=title_from_question(first_question),
            title_source="default",
            conversation_metadata={k: v for k, v in (metadata or {}).items() if v is not None},
            context={},
            message_count=0,
            last_message_at=now,
            created_at=now,
            updated_at=now,
        )
        db.add(conv)
        await db.commit()
        logger.info(f"Created conversation {conv.id}")
        return conv

    async def append_message(
        self,
        db: AsyncSession,
        conversation: Conversation,
        role: str,
        content: str,
        metadata: Optional[dict] = None,
    ) -> ConversationMessage:
        # Lock the row so concurrent appends cannot reuse a sequence number.
        locked = (await db.execute(
            select(Conversation).where(Conversation.id == conversation.id).with_for_update()
        )).scalar_one()
        now = _utcnow()
        sequence = locked.message_count + 1
        message = ConversationMessage(
            id=uuid4(),
            conversation_id=locked.id,
            organization_id=locked.organization_id,
            sequence=sequence,
            role=role,
            content=content,
            created_at=now,
            message_metadata=_json_safe(metadata or {}),
        )
        db.add(message)
        locked.message_count = sequence
        locked.last_message_at = now
        locked.updated_at = now
        await db.commit()
        return message

    async def save_context(self, db: AsyncSession, conversation: Conversation, context: dict) -> None:
        await db.execute(
            update(Conversation)
            .where(Conversation.id == conversation.id)
            .values(context=_json_safe(context))
        )
        await db.commit()

    async def rename(self, db: AsyncSession, conversation: Conversation, title: str) -> Conversation:
        cleaned = clean_title(title)
        if not cleaned:
            raise ValueError("Title cannot be empty")
        conversation.title = cleaned
        conversation.title_source = "user"
        conversation.updated_at = _utcnow()
        await db.commit()
        return conversation

    async def set_pinned(self, db: AsyncSession, conversation: Conversation, pinned: bool) -> Conversation:
        conversation.is_pinned = pinned
        conversation.pinned_at = _utcnow() if pinned else None
        conversation.updated_at = _utcnow()
        await db.commit()
        return conversation

    async def set_archived(self, db: AsyncSession, conversation: Conversation, archived: bool) -> Conversation:
        conversation.is_archived = archived
        if archived:
            # An archived conversation leaves the main list, so it cannot stay pinned.
            conversation.is_pinned = False
            conversation.pinned_at = None
        conversation.updated_at = _utcnow()
        await db.commit()
        return conversation

    async def apply_auto_title(self, db: AsyncSession, conversation_id: Any, title: str) -> bool:
        """Set a generated title unless the user has renamed the conversation."""
        cleaned = clean_title(title)
        if not cleaned:
            return False
        result = await db.execute(
            update(Conversation)
            .where(Conversation.id == _uuid(conversation_id), Conversation.title_source != "user")
            .values(title=cleaned, title_source="auto", updated_at=_utcnow())
        )
        await db.commit()
        return result.rowcount > 0

    async def soft_delete(
        self, db: AsyncSession, *, organization_id: Any, user_id: Any, conversation_ids: list[Any]
    ) -> int:
        ids = [_uuid(cid) for cid in conversation_ids]
        if not ids:
            return 0
        result = await db.execute(
            update(Conversation)
            .where(
                Conversation.id.in_(ids),
                Conversation.organization_id == _uuid(organization_id),
                Conversation.user_id == _uuid(user_id),
                Conversation.deleted_at.is_(None),
            )
            # Pin/archive state is kept so Undo restores exactly what was there;
            # every list query already excludes deleted rows.
            .values(deleted_at=_utcnow())
        )
        await db.commit()
        return result.rowcount

    async def restore(self, db: AsyncSession, conversation: Conversation) -> Conversation:
        conversation.deleted_at = None
        conversation.updated_at = _utcnow()
        await db.commit()
        return conversation

    async def purge_deleted(self, db: AsyncSession, *, older_than: timedelta) -> int:
        """Permanently remove conversations soft-deleted before the cutoff."""
        cutoff = _utcnow() - older_than
        result = await db.execute(
            delete(Conversation).where(
                Conversation.deleted_at.is_not(None), Conversation.deleted_at < cutoff
            )
        )
        await db.commit()
        return result.rowcount

    # ── reads ────────────────────────────────────────────────────────────────

    async def recent_history(
        self, db: AsyncSession, conversation: Conversation, turns: int
    ) -> list[dict[str, str]]:
        """Last ``turns`` user/assistant pairs, oldest first, for the LLM prompt."""
        rows = (await db.execute(
            select(ConversationMessage.role, ConversationMessage.content)
            .where(ConversationMessage.conversation_id == conversation.id)
            .order_by(ConversationMessage.sequence.desc())
            .limit(max(turns, 0) * 2)
        )).all()
        return [{"role": role, "content": content} for role, content in reversed(rows)]

    async def messages(
        self,
        db: AsyncSession,
        conversation: Conversation,
        *,
        limit: int = 200,
        before_sequence: Optional[int] = None,
    ) -> tuple[list[ConversationMessage], bool]:
        """A page of messages, oldest first, and whether older ones exist."""
        query = select(ConversationMessage).where(
            ConversationMessage.conversation_id == conversation.id
        )
        if before_sequence is not None:
            query = query.where(ConversationMessage.sequence < before_sequence)
        rows = (await db.execute(
            query.order_by(ConversationMessage.sequence.desc()).limit(limit + 1)
        )).scalars().all()
        has_more = len(rows) > limit
        return list(reversed(rows[:limit])), has_more

    async def list(
        self,
        db: AsyncSession,
        *,
        organization_id: Any,
        user_id: Any,
        limit: int = 30,
        cursor: Optional[str] = None,
        q: Optional[str] = None,
        archived: bool = False,
        pinned_only: bool = False,
        deleted: bool = False,
    ) -> tuple[list[dict[str, Any]], Optional[str]]:
        """Pinned first, then most recent. Keyset-paginated; ``q`` searches titles and messages."""
        conditions = [
            Conversation.organization_id == _uuid(organization_id),
            Conversation.user_id == _uuid(user_id),
        ]
        if deleted:
            conditions.append(Conversation.deleted_at.is_not(None))
        else:
            conditions.append(Conversation.deleted_at.is_(None))
            conditions.append(Conversation.is_archived.is_(archived))
        if pinned_only:
            conditions.append(Conversation.is_pinned.is_(True))

        tsquery = None
        if q and q.strip():
            q = q.strip()[:200]
            ts = _search_query(q)
            title_match = Conversation.title.ilike(f"%{_escape_like(q)}%", escape="\\")
            if ts:
                tsquery = func.to_tsquery("simple", ts)
                message_match = select(ConversationMessage.id).where(
                    ConversationMessage.conversation_id == Conversation.id,
                    ConversationMessage.search_vector.op("@@")(tsquery),
                ).exists()
                conditions.append(or_(title_match, message_match))
            else:
                conditions.append(title_match)

        if cursor:
            pinned, at, cid = _decode_cursor(cursor)
            conditions.append(
                tuple_(Conversation.is_pinned, Conversation.last_message_at, Conversation.id)
                < tuple_(pinned, at, cid)
            )

        rows = (await db.execute(
            select(Conversation)
            .where(and_(*conditions))
            .order_by(Conversation.is_pinned.desc(), Conversation.last_message_at.desc(),
                      Conversation.id.desc())
            .limit(limit + 1)
        )).scalars().all()
        page = list(rows[:limit])
        next_cursor = _encode_cursor(page[-1]) if len(rows) > limit and page else None

        ids = [conv.id for conv in page]
        previews = await self._previews(db, ids)
        snippets = await self._snippets(db, ids, tsquery) if tsquery is not None else {}
        return [
            summary(conv, preview=previews.get(conv.id), snippet=snippets.get(conv.id))
            for conv in page
        ], next_cursor

    async def _previews(self, db: AsyncSession, ids: list[UUID]) -> dict[UUID, str]:
        """Latest message per conversation in one query (DISTINCT ON)."""
        if not ids:
            return {}
        rows = (await db.execute(
            select(ConversationMessage.conversation_id,
                   func.left(ConversationMessage.content, PREVIEW_CHARS))
            .where(ConversationMessage.conversation_id.in_(ids))
            .order_by(ConversationMessage.conversation_id, ConversationMessage.sequence.desc())
            .distinct(ConversationMessage.conversation_id)
        )).all()
        return {cid: " ".join((content or "").split()) for cid, content in rows}

    async def _snippets(self, db: AsyncSession, ids: list[UUID], tsquery) -> dict[UUID, str]:
        """Best-matching message excerpt per conversation, with highlight markers."""
        if not ids:
            return {}
        rank = func.ts_rank(ConversationMessage.search_vector, tsquery)
        headline = func.ts_headline(
            "simple", ConversationMessage.content, tsquery,
            f"StartSel={HIGHLIGHT_START},StopSel={HIGHLIGHT_END},MaxWords=24,MinWords=8,MaxFragments=1",
        )
        rows = (await db.execute(
            select(ConversationMessage.conversation_id, headline)
            .where(
                ConversationMessage.conversation_id.in_(ids),
                ConversationMessage.search_vector.op("@@")(tsquery),
            )
            .order_by(ConversationMessage.conversation_id, rank.desc())
            .distinct(ConversationMessage.conversation_id)
        )).all()
        return {cid: " ".join((snippet or "").split()) for cid, snippet in rows}

    async def owner_stats(self, db: AsyncSession, *, organization_id: Any, user_id: Any) -> dict[str, int]:
        row = (await db.execute(
            select(
                func.count().filter(Conversation.deleted_at.is_(None)),
                func.count().filter(and_(Conversation.deleted_at.is_(None), Conversation.is_pinned)),
                func.count().filter(and_(Conversation.deleted_at.is_(None), Conversation.is_archived)),
                func.count().filter(Conversation.deleted_at.is_not(None)),
                func.coalesce(func.sum(Conversation.message_count).filter(
                    Conversation.deleted_at.is_(None)), 0),
            ).where(
                Conversation.organization_id == _uuid(organization_id),
                Conversation.user_id == _uuid(user_id),
            )
        )).one()
        return {"total": row[0], "pinned": row[1], "archived": row[2], "deleted": row[3],
                "messages": int(row[4])}


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _json_safe(value: Any) -> Any:
    """Round-trip through JSON so UUIDs/datetimes in metadata can be stored."""
    return json.loads(json.dumps(value, default=str))


# ── in-memory store for offline evaluation ──────────────────────────────────

@dataclass
class _MemConversation:
    id: UUID
    organization_id: UUID
    user_id: str
    title: str = DEFAULT_TITLE
    context: dict = field(default_factory=dict)
    conversation_metadata: dict = field(default_factory=dict)
    messages: list = field(default_factory=list)


class InMemoryConversationStore:
    """Same contract as the chat pipeline needs, nothing persisted.

    Used by the evaluation runner so golden-set runs exercise the real chat
    path without writing evaluation chats into a tenant's history.
    """

    def __init__(self) -> None:
        self._conversations: dict[UUID, _MemConversation] = {}

    async def get_owned(self, db, conversation_id, *, organization_id, user_id,
                        include_deleted: bool = False):
        conv = self._conversations.get(_uuid(conversation_id))
        return conv if conv and conv.user_id == str(user_id) else None

    async def exists_for_other_owner(self, db, conversation_id) -> bool:
        return False

    async def create(self, db, *, organization_id, user_id, first_question: str = "",
                     metadata: Optional[dict] = None):
        conv = _MemConversation(uuid4(), _uuid(organization_id), str(user_id),
                                title_from_question(first_question),
                                conversation_metadata=dict(metadata or {}))
        self._conversations[conv.id] = conv
        return conv

    async def append_message(self, db, conversation, role, content, metadata=None):
        conversation.messages.append({"role": role, "content": content, "metadata": metadata or {}})
        return conversation.messages[-1]

    async def recent_history(self, db, conversation, turns):
        return [{"role": m["role"], "content": m["content"]}
                for m in conversation.messages[-max(turns, 0) * 2:]] if turns else []

    async def save_context(self, db, conversation, context):
        conversation.context = dict(context)


conversation_store = ConversationStore()

__all__ = [
    "ConversationStore",
    "InMemoryConversationStore",
    "conversation_store",
    "summary",
    "message_dict",
    "title_from_question",
    "clean_title",
    "HIGHLIGHT_START",
    "HIGHLIGHT_END",
]
