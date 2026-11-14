"""
Reranking service — provider-agnostic.

Uses RERANK_PROVIDER / RERANK_MODEL (Cohere, Jina, Voyage, or any
Cohere-compatible /rerank endpoint such as Hugging Face TEI). When reranking
is disabled or the provider fails, chunks keep their fused order and are
flagged ``rerank_degraded`` so downstream relevance filtering switches to the
similarity floor instead of a cross-encoder threshold.
"""
from __future__ import annotations

from typing import Any, Optional

from loguru import logger

from app.core.config import settings
from app.services.ai import registry
from app.services.ai.types import ProviderError

_RERANK_TIMEOUT = 10.0   # seconds


class RerankingService:
    """Reranks retrieved chunks with the configured cross-encoder."""

    def __init__(self) -> None:
        self.top_n = settings.rerank_top_k

    @property
    def model(self) -> str:
        client = registry.rerank_client()
        return client.label if client else "none"

    @staticmethod
    def _document_text(chunk: dict[str, Any]) -> str:
        """What the cross-encoder reads: provenance, then the passage.

        Questions often name their source ("in the pricing module"); without
        the document title the reranker cannot use that. The section heading
        carries meaning the passage body often omits.
        """
        title = (chunk.get("document_name") or "").rsplit(".", 1)[0].replace("_", " ").strip()
        section = chunk.get("section_title")
        header = " | ".join(
            part for part in (f"Document: {title}" if title else "", f"Section: {section}" if section else "") if part
        )
        content = chunk.get("content", "")
        return f"{header}\n{content}" if header else content

    async def rerank(
        self,
        query: str,
        chunks: list[dict[str, Any]],
        top_n: Optional[int] = None,
    ) -> list[dict[str, Any]]:
        if not chunks:
            return []
        n = top_n or self.top_n
        client = registry.rerank_client()
        if client is None:
            return self._fallback_ranking(chunks, n)
        try:
            ranked = await client.rerank(
                query, [self._document_text(c) for c in chunks], top_n=n, timeout=_RERANK_TIMEOUT
            )
        except ProviderError as exc:
            logger.error(f"Reranking failed on {client.label} "
                         f"({'billing' if exc.billing else exc.status}) — using fused order")
            return self._fallback_ranking(chunks, n)
        reranked = []
        for index, score in ranked:
            if 0 <= index < len(chunks):
                chunk = chunks[index].copy()
                chunk["rerank_score"] = score
                chunk["rerank_position"] = index
                reranked.append(chunk)
        logger.info(f"✅ Reranked with {client.label}: {len(reranked)} results")
        return reranked

    async def rerank_with_threshold(
        self,
        query: str,
        chunks: list[dict[str, Any]],
        relevance_threshold: float = 0.5,
        top_n: Optional[int] = None,
    ) -> list[dict[str, Any]]:
        reranked = await self.rerank(query, chunks, top_n)
        return [c for c in reranked if c.get("rerank_score", 1.0) >= relevance_threshold]

    @staticmethod
    def _fallback_ranking(
        chunks: list[dict[str, Any]], n: int
    ) -> list[dict[str, Any]]:
        """Return top-n chunks in fused order, flagged as not reranked.

        No ``rerank_score`` is written: fused RRF and cosine scores are on a
        different scale from cross-encoder scores, and passing them off as
        rerank scores made the downstream relevance floor drop everything.
        """
        result = []
        for i, chunk in enumerate(chunks[:n]):
            c = chunk.copy()
            c["rerank_degraded"] = True
            c["rerank_position"] = i
            result.append(c)
        return result

    def calculate_score_statistics(self, chunks: list[dict]) -> dict:
        if not chunks:
            return {}
        scores = [c.get("rerank_score", 0) for c in chunks]
        sorted_scores = sorted(scores)
        return {
            "min_score": sorted_scores[0],
            "max_score": sorted_scores[-1],
            "avg_score": sum(scores) / len(scores),
            "median_score": sorted_scores[len(scores) // 2],
            "total_chunks": len(chunks),
        }


# Singleton
reranking_service = RerankingService()

__all__ = ["RerankingService", "reranking_service"]
