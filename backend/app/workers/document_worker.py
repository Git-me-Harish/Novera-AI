"""Redis Streams worker for document extraction, chunking and embedding."""
from __future__ import annotations

import asyncio
import json
import os
import time
from pathlib import Path
from uuid import UUID

import redis.asyncio as aioredis
from loguru import logger
from sqlalchemy import update

from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.models.document import Document
from app.services.document_processing.job_queue import (
    CONSUMER_GROUP,
    DEAD_LETTER_STREAM_KEY,
    METRICS_PREFIX,
    RETRY_ZSET_KEY,
    STREAM_KEY,
)
from app.services.document_processing.processor import document_processor


CONSUMER_NAME = os.getenv("DOCUMENT_WORKER_NAME", f"worker-{os.getpid()}")


async def _ensure_group(client) -> None:
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


async def _process_message(client, message_id: str, fields: dict[str, str]) -> None:
    document_id = UUID(fields["document_id"])
    operation = fields.get("operation", "process")
    logger.info("Processing document job {}: {} ({})", message_id, document_id, operation)

    try:
        if operation == "process":
            async with AsyncSessionLocal() as db:
                document = await db.get(Document, document_id)
                if document is None:
                    raise ValueError(f"Document {document_id} not found")
                # A worker can crash after committing and before XACK. Treat a
                # completed document as an idempotent success on redelivery.
                if document.status == "completed":
                    await client.xack(STREAM_KEY, CONSUMER_GROUP, message_id)
                    await client.incr(f"{METRICS_PREFIX}succeeded")
                    return
                await document_processor.process_document(
                    document_id, Path(document.file_path), db
                )
        elif operation == "reprocess":
            await document_processor.reprocess_document(document_id)
        else:
            raise ValueError(f"Unsupported document operation: {operation}")
    except Exception as exc:
        attempt = int(fields.get("attempt", "0")) + 1
        async with AsyncSessionLocal() as db:
            await db.execute(
                update(Document)
                .where(Document.id == document_id)
                .values(status="failed", processing_error=str(exc)[:500])
            )
            await db.commit()

        await client.incr(f"{METRICS_PREFIX}failed")
        if attempt >= settings.document_queue_max_attempts:
            await client.xadd(
                DEAD_LETTER_STREAM_KEY,
                {
                    **fields,
                    "attempt": str(attempt),
                    "error": str(exc)[:1000],
                    "failed_at": str(int(time.time())),
                },
                maxlen=10_000,
                approximate=True,
            )
            await client.xack(STREAM_KEY, CONSUMER_GROUP, message_id)
            await client.incr(f"{METRICS_PREFIX}dead_lettered")
            logger.error(
                "Document job moved to dead letter after {} attempts: {}",
                attempt,
                document_id,
            )
            return

        delay = min(
            settings.document_queue_retry_base_seconds * (2 ** (attempt - 1)),
            settings.document_queue_retry_max_seconds,
        )
        retry_at = time.time() + delay
        retry_payload = {**fields, "attempt": str(attempt)}
        await client.zadd(RETRY_ZSET_KEY, {json.dumps(retry_payload, sort_keys=True): retry_at})
        await client.xack(STREAM_KEY, CONSUMER_GROUP, message_id)
        await client.incr(f"{METRICS_PREFIX}retried")
        logger.warning(
            "Document job scheduled for retry {} in {}s (attempt {}/{}): {}",
            document_id,
            delay,
            attempt,
            settings.document_queue_max_attempts,
            exc,
        )
        return

    await client.xack(STREAM_KEY, CONSUMER_GROUP, message_id)
    await client.incr(f"{METRICS_PREFIX}succeeded")
    logger.info("Document job acknowledged: {}", message_id)


async def _drain_due_retries(client) -> None:
    due = await client.zrangebyscore(RETRY_ZSET_KEY, "-inf", time.time(), start=0, num=10)
    for raw_payload in due:
        try:
            await client.xadd(STREAM_KEY, json.loads(raw_payload), maxlen=100_000, approximate=True)
        except Exception:
            raise
        # Enqueue before removal: a worker crash can duplicate a retry, but
        # cannot lose it. Document processing is idempotent for completed jobs.
        await client.zrem(RETRY_ZSET_KEY, raw_payload)


_PURGE_INTERVAL_SECONDS = 3600
_last_purge = 0.0


async def _purge_deleted_conversations() -> None:
    """Hourly: permanently remove conversations past the restore window."""
    global _last_purge
    import time
    from datetime import timedelta

    if time.monotonic() - _last_purge < _PURGE_INTERVAL_SECONDS:
        return
    _last_purge = time.monotonic()
    try:
        from app.db.session import AsyncSessionLocal
        from app.services.generation.conversation_manager import conversation_store

        from app.services.tenancy import audit

        async with AsyncSessionLocal() as db:
            purged = await conversation_store.purge_deleted(
                db, older_than=timedelta(days=settings.conversation_delete_retention_days)
            )
            expired_audit = await audit.purge_expired(
                db, older_than=timedelta(days=settings.audit_retention_days)
            )
        if purged:
            logger.info("Purged {} conversations past the restore window", purged)
        if expired_audit:
            logger.info("Purged {} audit events past retention", expired_audit)
    except Exception as exc:  # retention must never stop document processing
        logger.error("Conversation purge failed: {}", type(exc).__name__)


async def run() -> None:
    client = aioredis.from_url(
        settings.redis_url,
        encoding="utf-8",
        decode_responses=True,
        socket_connect_timeout=5,
        socket_timeout=35,
        health_check_interval=30,
    )
    await client.ping()
    await _ensure_group(client)
    logger.info("Document worker ready as {}", CONSUMER_NAME)

    try:
        while True:
            await _purge_deleted_conversations()
            await _drain_due_retries(client)
            # Recover jobs left pending by a crashed worker, then consume new jobs.
            reclaimed = await client.xautoclaim(
                STREAM_KEY,
                CONSUMER_GROUP,
                CONSUMER_NAME,
                min_idle_time=60_000,
                start_id="0-0",
                count=10,
            )
            for message_id, fields in reclaimed[1]:
                await _process_message(client, message_id, fields)

            messages = await client.xreadgroup(
                CONSUMER_GROUP,
                CONSUMER_NAME,
                {STREAM_KEY: ">"},
                count=1,
                block=5_000,
            )
            for _, entries in messages or []:
                for message_id, fields in entries:
                    await _process_message(client, message_id, fields)
    finally:
        await client.aclose()


if __name__ == "__main__":
    asyncio.run(run())
