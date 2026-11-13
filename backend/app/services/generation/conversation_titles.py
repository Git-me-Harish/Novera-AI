"""Background generation of conversation titles.

Runs after the first grounded answer so the reply is never delayed. Uses the
organization's own model chain: a tenant that brought its own model for data
residency must not have its questions sent to the platform model for titling.
A title the user typed is never overwritten (enforced in the store's UPDATE).
"""
from __future__ import annotations

import asyncio
from typing import Any

from loguru import logger

from app.core.config import settings

_TITLE_PROMPT = (
    "Write a short title, at most 6 words, for a conversation that starts with the "
    "question below. Use the question's language. Reply with the title only — no quotes, "
    "no punctuation at the end.\n\nQuestion: {question}"
)

# Strong references: the event loop only keeps weak ones to running tasks.
_pending: set[asyncio.Task] = set()


async def generate_title(organization_id: Any, conversation_id: Any, question: str) -> None:
    from app.db.session import AsyncSessionLocal
    from app.services.ai.registry import chat_chain_for
    from app.services.generation.conversation_manager import conversation_store
    from app.services.generation.llm_service import llm_service

    try:
        async with AsyncSessionLocal() as db:
            chain = await chat_chain_for(db, organization_id)
            result = await llm_service.complete(
                _TITLE_PROMPT.format(question=question[:1000]),
                chain=chain, temperature=0.2, max_tokens=24, timeout=10.0, use_cache=False,
            )
            if result is None or not result.text:
                return
            if await conversation_store.apply_auto_title(db, conversation_id, result.text):
                logger.info(f"Auto-titled conversation {conversation_id}")
    except Exception as exc:  # a title is cosmetic; never surface failures
        logger.warning(f"Auto-title skipped for {conversation_id}: {type(exc).__name__}")


def schedule_title(organization_id: Any, conversation_id: Any, question: str) -> None:
    if not settings.conversation_auto_title:
        return
    try:
        task = asyncio.get_running_loop().create_task(
            generate_title(organization_id, conversation_id, question)
        )
    except RuntimeError:
        return
    _pending.add(task)
    task.add_done_callback(_pending.discard)
