"""
Redis-backed conversation manager.

Every conversation is persisted to Redis (or the in-memory fallback when
Redis is unavailable) so all Gunicorn workers share the same session state.

CRITICAL FIX (this version):
  - create_conversation() is now `async` so the Redis write is *awaited*
    before control returns to the caller.  The previous fire-and-forget
    loop.create_task() pattern raced with the immediately-following
    add_message() read, causing "re-creating shell / user_id=unknown" bugs
    under any concurrency.
  - max_messages raised from 10 → 20 (10 was too low — only 5 turns before
    context silently dropped).
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import uuid4

from loguru import logger

from app.core.redis_manager import redis_manager

# Namespace prefix in Redis
_PREFIX = "conv:"
# How long (seconds) an idle conversation lives in Redis
_DEFAULT_TTL = 7200  # 2 hours


class ConversationManager:
    """
    Manages conversation state and history for chat sessions.
    Persists to Redis so all workers share session state.
    Falls back to the RedisManager's in-memory store automatically
    when Redis is unavailable.
    """

    def __init__(self) -> None:
        self.max_messages = 20   # 10 full user/assistant turns before trimming
        self.ttl = _DEFAULT_TTL


    @staticmethod
    def _key(conversation_id: str) -> str:
        return f"{_PREFIX}{conversation_id}"

    async def _load(self, conversation_id: str) -> Optional[dict]:
        return await redis_manager.get_json(self._key(conversation_id))

    async def _save(self, conv: dict) -> None:
        await redis_manager.set_json(
            self._key(conv["id"]), conv, ttl=self.ttl
        )

    async def create_conversation(
        self,
        user_id: str,
        metadata: Optional[dict] = None,
    ) -> str:
        """
        Create and immediately persist a new conversation session.

        FIXED: previously sync with fire-and-forget task for the Redis write.
        That race caused the next add_message() call (which does _load first)
        to find nothing and silently re-create a shell with user_id='unknown'.
        Now fully async — callers must await it.
        """
        conversation_id = str(uuid4())
        conv = {
            "id": conversation_id,
            "user_id": user_id,
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
            "messages": [],
            "metadata": metadata or {},
            "context": {},
        }
        await self._save(conv)   # guaranteed write before returning
        logger.info(f"Created conversation {conversation_id} for user {user_id}")
        return conversation_id

    async def add_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        metadata: Optional[dict] = None,
    ) -> dict:
        """Add a message to conversation history and persist."""
        conv = await self._load(conversation_id)

        if conv is None:
            # Defensive fallback — should not happen after the async-create fix.
            logger.warning(
                f"Conversation {conversation_id} not in store; re-creating shell."
            )
            conv = {
                "id": conversation_id,
                "user_id": "unknown",
                "created_at": datetime.utcnow().isoformat(),
                "updated_at": datetime.utcnow().isoformat(),
                "messages": [],
                "metadata": {},
                "context": {},
            }

        message = {
            "id": str(uuid4()),
            "role": role,
            "content": content,
            "timestamp": datetime.utcnow().isoformat(),
            "metadata": metadata or {},
        }

        conv["messages"].append(message)
        conv["updated_at"] = datetime.utcnow().isoformat()

        # Update context shortcuts from assistant metadata
        if metadata and "context_used" in metadata:
            ctx = metadata["context_used"]
            if "primary_document" in ctx:
                conv["context"]["primary_document"] = ctx["primary_document"]
            if "active_documents" in ctx:
                conv["context"]["active_documents"] = ctx["active_documents"]

        # Hard cap: keep first message + last (max-1) to preserve opening context
        if len(conv["messages"]) > self.max_messages:
            conv["messages"] = (
                conv["messages"][:1] + conv["messages"][-(self.max_messages - 1):]
            )

        await self._save(conv)
        logger.debug(f"Added {role} message to conversation {conversation_id}")
        return message

    async def get_conversation(self, conversation_id: str) -> Optional[dict]:
        return await self._load(conversation_id)

    async def get_history(
        self,
        conversation_id: str,
        limit: Optional[int] = None,
    ) -> list[dict[str, str]]:
        """Return messages formatted as {role, content} for LLM APIs."""
        conv = await self._load(conversation_id)
        if not conv:
            return []

        messages = conv["messages"]
        if limit:
            messages = messages[-(limit * 2):]

        return [{"role": m["role"], "content": m["content"]} for m in messages]

    async def update_context(
        self, conversation_id: str, context_updates: dict
    ) -> None:
        conv = await self._load(conversation_id)
        if not conv:
            return
        conv["context"] = {**conv.get("context", {}), **context_updates}
        conv["updated_at"] = datetime.utcnow().isoformat()
        await self._save(conv)

    async def get_context(self, conversation_id: str) -> dict:
        conv = await self._load(conversation_id)
        return conv.get("context", {}) if conv else {}

    async def delete_conversation(self, conversation_id: str) -> bool:
        await redis_manager.delete(self._key(conversation_id))
        logger.info(f"Deleted conversation {conversation_id}")
        return True

    async def list_user_conversations(
        self, user_id: str, limit: int = 10
    ) -> list[dict]:
        """
        List conversations for a user.
        NOTE: Redis KEYS scan is O(N total keys) — acceptable for expected
        conversation volumes. For very high scale, switch to a per-user
        sorted-set index.
        """
        keys = await redis_manager.keys(f"{_PREFIX}*")
        convs = []
        for key in keys:
            data = await redis_manager.get_json(key)
            if data and data.get("user_id") == user_id:
                convs.append(data)

        convs.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
        return convs[:limit]

    async def summarize_conversation(self, conversation_id: str) -> dict:
        conv = await self._load(conversation_id)
        if not conv:
            return {}

        messages = conv["messages"]
        user_msgs = [m for m in messages if m["role"] == "user"]
        asst_msgs = [m for m in messages if m["role"] == "assistant"]

        return {
            "conversation_id": conversation_id,
            "total_messages": len(messages),
            "user_messages": len(user_msgs),
            "assistant_messages": len(asst_msgs),
            "topics_discussed": conv.get("context", {}).get("topics", []),
            "created_at": conv.get("created_at"),
            "last_activity": conv.get("updated_at"),
        }


# Singleton
conversation_manager = ConversationManager()

__all__ = ["ConversationManager", "conversation_manager"]
