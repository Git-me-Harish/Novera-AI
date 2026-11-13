"""
Embedding service — provider-agnostic.

The model comes from EMBEDDING_PROVIDER / EMBEDDING_MODEL (see
app.services.ai.registry). Every stored chunk is stamped with
(provider, model, dimensions) and vector search only compares vectors with
the same stamp, so switching models requires re-embedding — the service
never pads, truncates or falls back to a different model.
"""
from __future__ import annotations

import hashlib
from typing import Any, Optional

import numpy as np
from loguru import logger

from app.core.config import settings
from app.services.ai import registry
from app.services.ai.catalog import provider_info
from app.services.ai.types import ProviderError, ProviderNotConfigured


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

    async def _embed(self, texts: list[str], task: str) -> list[list[float]]:
        try:
            return await registry.embedding_client().embed(texts, task=task)
        except ProviderNotConfigured:
            raise
        except ProviderError as exc:
            raise RuntimeError(
                f"Embedding provider unavailable for {self.provider}:{self.model_name} "
                f"({'billing' if exc.billing else 'HTTP ' + str(exc.status)}); retry instead "
                "of mixing embedding spaces"
            ) from exc

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
        if not context:
            return text
        parts = []
        if context.get("document_title"):
            parts.append(f"Document: {context['document_title']}")
        if context.get("section"):
            parts.append(f"Section: {context['section']}")
        if context.get("page"):
            parts.append(f"Page: {context['page']}")
        if context.get("chunk_type") and context["chunk_type"] != "text":
            parts.append(f"Type: {context['chunk_type']}")
        if parts:
            return " | ".join(parts) + "\n\n" + text
        return text

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

__all__ = ["EmbeddingService", "embedding_service"]
