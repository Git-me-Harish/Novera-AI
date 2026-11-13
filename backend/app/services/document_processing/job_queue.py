"""Durable document-processing queue backed by Redis Streams.

The API process only enqueues jobs. Processing is performed by a separate
worker so uploads cannot be lost when an API worker restarts or is redeployed.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from loguru import logger

from app.core.redis_manager import redis_manager


STREAM_KEY = "novera:document-processing"
CONSUMER_GROUP = "document-processors"
RETRY_ZSET_KEY = "novera:document-processing:retries"
DEAD_LETTER_STREAM_KEY = "novera:document-processing:dead-letter"
METRICS_PREFIX = "novera:document-processing:metrics:"


class DocumentJobQueue:
    async def _client_and_group(self) -> Any:
        if not redis_manager.is_redis_active or redis_manager._client is None:
            raise RuntimeError("Durable document queue requires an available Redis connection")

        client = redis_manager._client
        try:
            await client.xgroup_create(
                name=STREAM_KEY,
                groupname=CONSUMER_GROUP,
                id="0",
                mkstream=True,
            )
        except Exception as exc:
            if "BUSYGROUP" not in str(exc):
                raise
        return client

    async def enqueue(self, document_id: UUID, operation: str = "process") -> str:
        if operation not in {"process", "reprocess"}:
            raise ValueError(f"Unsupported document operation: {operation}")
        client = await self._client_and_group()
        message_id = await client.xadd(
            STREAM_KEY,
            {"document_id": str(document_id), "operation": operation, "attempt": "0"},
            maxlen=100_000,
            approximate=True,
        )
        logger.info("Document job enqueued: {} ({})", document_id, operation)
        return str(message_id)


document_job_queue = DocumentJobQueue()

__all__ = [
    "STREAM_KEY",
    "CONSUMER_GROUP",
    "RETRY_ZSET_KEY",
    "DEAD_LETTER_STREAM_KEY",
    "METRICS_PREFIX",
    "DocumentJobQueue",
    "document_job_queue",
]
