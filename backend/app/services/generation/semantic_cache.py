"""Tenant-scoped semantic response cache for grounded document answers."""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from loguru import logger
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.document import Chunk, Document
from app.models.response_cache import ResponseCacheEntry
from app.services.embedding.embedding_service import embedding_service


class SemanticCache:
    """A conservative answer cache that never crosses tenant/corpus boundaries."""

    def scope_key(self, doc_type: str | None, department: str | None) -> str:
        raw = f"doc_type={doc_type or '*'}|department={department or '*'}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    async def corpus_fingerprint(
        self, db: AsyncSession, organization_id: UUID
    ) -> str:
        result = await db.execute(
            select(
                func.count(Document.id),
                func.max(Document.processed_date),
                func.max(Document.file_hash),
            ).where(
                Document.organization_id == organization_id,
                Document.status == "completed",
            )
        )
        count, latest_processed, latest_hash = result.one()
        # Chunk edits change answers without touching the document row, so
        # the fingerprint must also move when any chunk is edited.
        chunk_result = await db.execute(
            select(func.count(Chunk.id), func.max(Chunk.edited_at))
            .join(Document, Chunk.document_id == Document.id)
            .where(
                Document.organization_id == organization_id,
                Document.status == "completed",
            )
        )
        chunk_count, latest_edit = chunk_result.one()
        raw = "|".join(
            [
                str(count or 0),
                latest_processed.isoformat() if latest_processed else "",
                str(latest_hash or ""),
                str(chunk_count or 0),
                latest_edit.isoformat() if latest_edit else "",
            ]
        )
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    async def lookup(
        self,
        db: AsyncSession,
        *,
        organization_id: UUID,
        query: str,
        query_embedding: list[float],
        scope_key: str,
        corpus_fingerprint: str,
        generation_model: str,
    ) -> dict[str, Any] | None:
        if not settings.semantic_cache_enabled:
            return None
        now = datetime.now(timezone.utc)
        distance = ResponseCacheEntry.query_embedding.cosine_distance(query_embedding)
        result = await db.execute(
            select(ResponseCacheEntry, distance.label("distance"))
            .where(
                ResponseCacheEntry.organization_id == organization_id,
                ResponseCacheEntry.scope_key == scope_key,
                ResponseCacheEntry.corpus_fingerprint == corpus_fingerprint,
                ResponseCacheEntry.embedding_provider == embedding_service.provider,
                ResponseCacheEntry.embedding_model == embedding_service.model_name,
                ResponseCacheEntry.embedding_dimensions == embedding_service.dimensions,
                # Model switches (per tenant) must not serve another model's answers.
                ResponseCacheEntry.generation_model == generation_model,
                ResponseCacheEntry.expires_at > now,
            )
            .order_by(distance)
            .limit(1)
        )
        row = result.first()
        if not row:
            return None
        entry, raw_distance = row
        similarity = 1.0 - float(raw_distance)
        if similarity < settings.semantic_cache_similarity_threshold:
            return None
        await db.execute(
            update(ResponseCacheEntry)
            .where(ResponseCacheEntry.id == entry.id)
            .values(
                last_hit_at=now,
                hit_count=ResponseCacheEntry.hit_count + 1,
            )
        )
        await db.flush()
        return {
            "answer": entry.answer,
            "sources": entry.sources or [],
            "citations": entry.citations or [],
            "similarity": similarity,
            "cache_hit": True,
            "cache_entry_id": str(entry.id),
        }

    async def store(
        self,
        db: AsyncSession,
        *,
        organization_id: UUID,
        query: str,
        query_embedding: list[float],
        scope_key: str,
        corpus_fingerprint: str,
        generation_model: str,
        answer: str,
        sources: list[dict[str, Any]],
        citations: list[dict[str, Any]],
    ) -> None:
        if not settings.semantic_cache_enabled or not answer.strip() or not sources:
            return
        now = datetime.now(timezone.utc)
        entry = ResponseCacheEntry(
            organization_id=organization_id,
            scope_key=scope_key,
            query_hash=hashlib.sha256(query.encode("utf-8")).hexdigest(),
            query_embedding=query_embedding,
            embedding_provider=embedding_service.provider,
            embedding_model=embedding_service.model_name,
            embedding_dimensions=embedding_service.dimensions,
            corpus_fingerprint=corpus_fingerprint,
            generation_model=generation_model,
            answer=answer,
            sources=sources,
            citations=citations,
            entry_metadata={"cache_version": "semantic-v1"},
            created_at=now,
            expires_at=now + timedelta(seconds=settings.semantic_cache_ttl_seconds),
            hit_count=0,
        )
        db.add(entry)
        await db.flush()


semantic_cache = SemanticCache()
