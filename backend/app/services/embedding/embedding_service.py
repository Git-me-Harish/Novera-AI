"""
Embedding service — provider-agnostic.

The model comes from EMBEDDING_PROVIDER / EMBEDDING_MODEL (see
app.services.ai.registry). Every stored chunk is stamped with
(provider, model, dimensions) and vector search only compares vectors with
the same stamp, so switching models requires re-embedding — the service
never pads, truncates or falls back to a different model.
"""
from __future__ import annotations

import asyncio
import hashlib
from typing import Any, Optional

import numpy as np
from loguru import logger

from app.core.config import settings
from app.services.ai import registry
from app.services.ai.catalog import provider_info
from app.services.ai.types import ProviderError, ProviderNotConfigured


def chunk_embedding_text(
    content: str,
    *,
    document_title: Optional[str] = None,
    section: Optional[str] = None,
    page: Optional[int] = None,
    chunk_type: Optional[str] = None,
) -> str:
    """The exact text a chunk is embedded as: a short provenance header plus
    the content. Ingestion, chunk edits, reverts and re-embedding all use this,
    so every vector of a corpus lives in the same text distribution."""
    parts = []
    if document_title:
        parts.append(f"Document: {document_title}")
    if section:
        parts.append(f"Section: {section}")
    if page:
        parts.append(f"Page: {page}")
    if chunk_type and chunk_type != "text":
        parts.append(f"Type: {chunk_type}")
    return (" | ".join(parts) + "\n\n" + content) if parts else content


def chunk_embedding_text_for(chunk: Any, document_title: Optional[str]) -> str:
    """chunk_embedding_text for a stored Chunk row (or a dict with the same keys)."""
    get = chunk.get if isinstance(chunk, dict) else lambda key, default=None: getattr(chunk, key, default)
    pages = get("page_numbers") or []
    return chunk_embedding_text(
        get("content") or "",
        document_title=document_title,
        section=get("section_title"),
        page=pages[0] if pages else None,
        chunk_type=get("chunk_type", "text"),
    )


class EmbeddingService:
    """Query and document embeddings in one consistent vector space."""

    # Kept for the diagnostics endpoint; a local fallback is never used.
    use_local_fallback = False

    @property
    def configured(self) -> bool:
        return registry.platform_embedding_spec() is not None

    @property
    def provider(self) -> str:
        spec = registry.platform_embedding_spec()
        return registry.embedding_storage_identity(spec)[0] if spec else "unconfigured"

    @property
    def model_name(self) -> str:
        spec = registry.platform_embedding_spec()
        return registry.embedding_storage_identity(spec)[1] if spec else "unconfigured"

    @property
    def dimensions(self) -> int:
        return settings.embedding_dimensions

    def _query_prefix(self) -> str:
        spec = registry.platform_embedding_spec()
        if spec is None:
            return ""
        # Gemini query vectors in the existing index were built with this
        # prefix; other providers default to the raw query.
        default = "Query: " if provider_info(spec.provider).id == "gemini" else ""
        return spec.option("query_prefix", default)

    # Transient failures (rate limits, timeouts, 5xx) are retried with
    # backoff. Ingestion can wait; a user's query gets one quick retry.
    _ATTEMPTS = {"document": 5, "query": 2}
    _MAX_WAIT_SECONDS = {"document": 60.0, "query": 2.0}
    # A user waits on a query embedding; a stalled provider must not hold
    # the request for the client's 60 s default (twice, with the retry).
    _TIMEOUT_SECONDS = {"document": 120.0, "query": 10.0}

    async def _embed(self, texts: list[str], task: str) -> list[list[float]]:
        attempts = self._ATTEMPTS.get(task, 1)
        for attempt in range(1, attempts + 1):
            try:
                return await registry.embedding_client().embed(
                    texts, task=task, timeout=self._TIMEOUT_SECONDS.get(task, 60.0)
                )
            except ProviderNotConfigured:
                raise
            except ProviderError as exc:
                if exc.retryable and not exc.billing and attempt < attempts:
                    wait = min(self._MAX_WAIT_SECONDS[task], exc.retry_after or 2.0 ** attempt)
                    logger.warning(
                        f"Embedding call failed ({exc.status or 'network'}); retry {attempt}/{attempts - 1} in {wait:.0f}s"
                    )
                    await asyncio.sleep(wait)
                    continue
                raise RuntimeError(
                    f"Embedding provider unavailable for {self.provider}:{self.model_name} "
                    f"({'billing' if exc.billing else 'HTTP ' + str(exc.status)}); retry instead "
                    "of mixing embedding spaces"
                ) from exc
        raise AssertionError("unreachable")

    # ── Public API ────────────────────────────────────────────────────────────

    async def embed_query(self, query: str) -> list[float]:
        """Embed a search query, with a Redis cache keyed by model identity."""
        cache_key = self._query_cache_key(query)
        try:
            from app.core.redis_manager import redis_manager

            cached = await redis_manager.get_json(cache_key)
            if isinstance(cached, list) and len(cached) == self.dimensions:
                return [float(value) for value in cached]
        except Exception as exc:
            logger.debug(f"Query embedding cache lookup skipped: {type(exc).__name__}")

        embedding = (await self._embed([f"{self._query_prefix()}{query}"], "query"))[0]
        try:
            from app.core.redis_manager import redis_manager

            await redis_manager.set_json(
                cache_key, embedding, ttl=settings.embedding_cache_ttl_seconds
            )
        except Exception as exc:
            logger.debug(f"Query embedding cache write skipped: {type(exc).__name__}")
        return embedding

    def _query_cache_key(self, query: str) -> str:
        normalized = " ".join((query or "").split()).casefold()
        query_hash = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
        return (
            "embedding_cache:query:"
            f"{self.provider}:{self.model_name}:{self.dimensions}:{query_hash}"
        )

    async def generate_embedding(self, text: str) -> list[float]:
        """Embed a single document chunk."""
        return (await self._embed([text], "document"))[0]

    async def generate_embeddings_batch(
        self, texts: list[str], show_progress: bool = False
    ) -> list[list[float]]:
        """Embed many document chunks; returns exactly one vector per text."""
        if not texts:
            return []
        if show_progress:
            logger.info(f"Embedding {len(texts)} texts with {self.provider}:{self.model_name}")
        return await self._embed(texts, "document")

    def enhance_text_for_embedding(
        self, text: str, context: Optional[dict[str, Any]] = None
    ) -> str:
        context = context or {}
        return chunk_embedding_text(
            text,
            document_title=context.get("document_title"),
            section=context.get("section"),
            page=context.get("page"),
            chunk_type=context.get("chunk_type"),
        )

    async def embed_chunks_with_context(
        self, chunks: list[dict], document_title: Optional[str] = None
    ) -> list[dict]:
        texts = [
            self.enhance_text_for_embedding(
                chunk["content"],
                {
                    "document_title": document_title,
                    "section": chunk.get("section_title"),
                    "page": (chunk.get("page_numbers") or [None])[0],
                    "chunk_type": chunk.get("chunk_type", "text"),
                },
            )
            for chunk in chunks
        ]
        embeddings = await self.generate_embeddings_batch(texts, show_progress=True)
        if len(embeddings) != len(chunks):
            # zip() would silently attach vectors to the wrong chunks.
            raise RuntimeError(
                f"Embedding count mismatch: {len(embeddings)} vectors for {len(chunks)} chunks"
            )
        for chunk, emb in zip(chunks, embeddings):
            chunk["embedding"] = emb
        return chunks

    @staticmethod
    def cosine_similarity(v1: list[float], v2: list[float]) -> float:
        a, b = np.array(v1), np.array(v2)
        n1, n2 = np.linalg.norm(a), np.linalg.norm(b)
        if n1 == 0 or n2 == 0:
            return 0.0
        return float(np.dot(a, b) / (n1 * n2))


# Singleton
embedding_service = EmbeddingService()

__all__ = ["EmbeddingService", "embedding_service", "chunk_embedding_text", "chunk_embedding_text_for"]
