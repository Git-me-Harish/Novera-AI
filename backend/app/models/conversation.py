"""Durable, tenant-scoped chat history."""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    Computed,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    false,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR, UUID
from sqlalchemy.orm import relationship

from app.db.session import Base

TITLE_MAX_LENGTH = 200
DEFAULT_TITLE = "New conversation"
_EMPTY_JSON = text("'{}'::jsonb")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Conversation(Base):
    """One chat thread, owned by a user inside one organization."""

    __tablename__ = "conversations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    organization_id = Column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    title = Column(String(TITLE_MAX_LENGTH), nullable=False, default=DEFAULT_TITLE)
    # default = placeholder/first-question, auto = generated, user = renamed.
    # Generated titles never overwrite a title the user chose.
    title_source = Column(String(16), nullable=False, default="default", server_default="default")

    is_pinned = Column(Boolean, nullable=False, default=False, server_default=false())
    pinned_at = Column(DateTime(timezone=True), nullable=True)
    is_archived = Column(Boolean, nullable=False, default=False, server_default=false())

    # Denormalized so the list view never scans messages.
    message_count = Column(Integer, nullable=False, default=0, server_default="0")
    last_message_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow,
                             server_default=func.now())

    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow,
                        server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow,
                        server_default=func.now())
    # Soft delete: restorable until purged by the retention job.
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    conversation_metadata = Column("metadata", JSONB, nullable=False, default=dict, server_default=_EMPTY_JSON)
    # Retrieval working memory (primary/active documents, entities) so
    # follow-up questions keep their document focus across sessions.
    context = Column(JSONB, nullable=False, default=dict, server_default=_EMPTY_JSON)

    messages = relationship(
        "ConversationMessage",
        back_populates="conversation",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="ConversationMessage.sequence",
    )

    __table_args__ = (
        CheckConstraint("title_source IN ('default', 'auto', 'user')", name="ck_conversations_title_source"),
        CheckConstraint("message_count >= 0", name="ck_conversations_message_count"),
        # The sidebar query: my live conversations, pinned first, most recent next.
        Index(
            "ix_conversations_owner_recent",
            "organization_id", "user_id", "is_pinned", "last_message_at",
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index("ix_conversations_deleted_at", "deleted_at",
              postgresql_where=text("deleted_at IS NOT NULL")),
        Index("ix_conversations_title_trgm", "title",
              postgresql_using="gin", postgresql_ops={"title": "gin_trgm_ops"}),
    )

    def __repr__(self) -> str:
        return f"<Conversation(id={self.id}, messages={self.message_count})>"


class ConversationMessage(Base):
    """One turn. ``sequence`` gives a stable, gap-free order per conversation."""

    __tablename__ = "conversation_messages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    conversation_id = Column(
        UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )
    # Denormalized tenant key: search and audits can scope by tenant without a join.
    organization_id = Column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    sequence = Column(Integer, nullable=False)
    role = Column(String(16), nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow,
                        server_default=func.now())
    message_metadata = Column("metadata", JSONB, nullable=False, default=dict,
                              server_default=_EMPTY_JSON)
    # 'simple' config: no language-specific stemming, so search works for any language.
    search_vector = Column(
        TSVECTOR, Computed("to_tsvector('simple', coalesce(content, ''))", persisted=True)
    )

    conversation = relationship("Conversation", back_populates="messages")

    __table_args__ = (
        UniqueConstraint("conversation_id", "sequence", name="uq_conversation_messages_sequence"),
        CheckConstraint("role IN ('user', 'assistant', 'system')", name="ck_conversation_messages_role"),
        Index("ix_conversation_messages_search", "search_vector", postgresql_using="gin"),
        Index("ix_conversation_messages_org", "organization_id"),
    )
