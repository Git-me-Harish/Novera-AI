"""Hybrid retrieval: dense + sparse, fused with weighted Reciprocal Rank Fusion.

The query embedding (a network call) and the keyword query (a database
call) run concurrently; the vector query waits for both, so one database
session is never used by two statements at once. Each search isolates its
own failure in a SAVEPOINT: if the embedding provider is down, keyword
results still come back, and nothing the request wrote earlier is undone.
"""
from __future__ import annotations

import asyncio
import time
from typing import Any, Dict, List, Optional
from uuid import UUID

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.rag_trace import get_current_trace, hash_value
from app.services.embedding.embedding_service import embedding_service
from app.services.retrieval.keyword_search import keyword_search_service
from app.services.retrieval.vector_search import vector_search_service

RRF_K = 60
BOOST_FACTOR = 1.3
EXPAND_TOP = 5


def _stage(name: str, started: float, **fields: Any) -> None:
    """Record a stage's latency in the request's RAG trace (stages map)."""
    trace = get_current_trace()
    if trace:
        trace.stage_end(name, started, **fields)


class HybridSearchService:
    def __init__(self) -> None:
        self.alpha = settings.hybrid_alpha  # weight of the dense ranking
        self.top_k = settings.retrieval_top_k
        self.rrf_k = RRF_K

    async def _embed(self, query: str, query_embedding: Optional[List[float]]) -> Optional[List[float]]:
        if query_embedding is not None:
            return query_embedding
        started = time.perf_counter()
        try:
            vector = await embedding_service.embed_query(query)
            _stage("query_embedding", started)
            return vector
        except Exception as exc:
            logger.error(f"Query embedding failed ({type(exc).__name__}); keyword results only")
            trace = get_current_trace()
            if trace:
                trace.event("semantic_degraded", status="degraded", reason=type(exc).__name__)
            return None

    async def search(
        self,
        query: str,
        db: AsyncSession,
        organization_id: UUID,
        top_k: Optional[int] = None,
        use_semantic: bool = True,
        use_keyword: bool = True,
        doc_type: Optional[str] = None,
        department: Optional[str] = None,
        document_filter: Optional[List[str]] = None,
        boost_documents: Optional[List[str]] = None,
        query_embedding: Optional[List[float]] = None,
    ) -> List[Dict[str, Any]]:
        k = top_k or self.top_k
        logger.info(f"Hybrid search: query_hash={hash_value(query)} k={k}")

        async def keyword() -> List[Dict[str, Any]]:
            if not use_keyword:
                return []
            started = time.perf_counter()
            rows = await keyword_search_service.search_keywords(
                query=query, db=db, organization_id=organization_id, top_k=k,
                doc_type=doc_type, department=department, document_filter=document_filter,
            )
            _stage("keyword_search", started, results=len(rows))
            return rows

        async def embed() -> Optional[List[float]]:
            return await self._embed(query, query_embedding) if use_semantic else None

        keyword_results, vector = await asyncio.gather(keyword(), embed())

        semantic_results: List[Dict[str, Any]] = []
        if vector is not None:
            started = time.perf_counter()
            semantic_results = await vector_search_service.search_similar_chunks(
                query_embedding=vector, db=db, organization_id=organization_id, top_k=k * 2,
                doc_type=doc_type, department=department, document_filter=document_filter,
            )
            _stage("vector_search", started, results=len(semantic_results))

        fused: Dict[str, Dict[str, Any]] = {}
        for rank, chunk in enumerate(semantic_results, 1):
            entry = fused.setdefault(chunk["chunk_id"], dict(chunk))
            entry["semantic_rank"] = rank
            entry["semantic_score"] = chunk["similarity_score"]
        for rank, chunk in enumerate(keyword_results, 1):
            entry = fused.setdefault(chunk["chunk_id"], dict(chunk))
            entry["keyword_rank"] = rank
            entry["keyword_score"] = chunk.get("keyword_score", 0.0)

        self._reciprocal_rank_fusion(fused, boost_documents)
        results = sorted(fused.values(), key=lambda c: c["fused_score"], reverse=True)[:k]
        logger.info(
            f"Hybrid search: {len(semantic_results)} dense + {len(keyword_results)} sparse -> {len(results)}"
        )
        return results

    def _reciprocal_rank_fusion(
        self, results: Dict[str, Dict[str, Any]], boost_documents: Optional[List[str]] = None
    ) -> Dict[str, Dict[str, Any]]:
        """score = alpha / (k + dense_rank) + (1 - alpha) / (k + sparse_rank)."""
        boosted_names = [b.casefold() for b in (boost_documents or []) if b]
        for chunk in results.values():
            score = 0.0
            if "semantic_rank" in chunk:
                score += self.alpha / (self.rrf_k + chunk["semantic_rank"])
            if "keyword_rank" in chunk:
                score += (1 - self.alpha) / (self.rrf_k + chunk["keyword_rank"])
            if boosted_names:
                name = (chunk.get("document_name") or "").casefold()
                chunk["boosted"] = any(b == name or b in name for b in boosted_names)
                if chunk["boosted"]:
                    score *= BOOST_FACTOR
            chunk["fused_score"] = score
            chunk["retrieval_method"] = [
                method for method, key in (("semantic", "semantic_rank"), ("keyword", "keyword_rank")) if key in chunk
            ]
        return results

    async def search_with_context_expansion(
        self,
        query: str,
        db: AsyncSession,
        organization_id: UUID,
        top_k: Optional[int] = None,
        expand_neighbors: bool = True,
        use_semantic: bool = True,
        use_keyword: bool = True,
        doc_type: Optional[str] = None,
        department: Optional[str] = None,
        document_filter: Optional[List[str]] = None,
        boost_documents: Optional[List[str]] = None,
        query_embedding: Optional[List[float]] = None,
    ) -> List[Dict[str, Any]]:
        """Hybrid results plus the same-section neighbours of the top hits.

        A section longer than one chunk continues in its neighbour; adding it
        lets the reranker see the rest of the answer. Neighbours are fetched
        for all top hits in a single query.
        """
        results = await self.search(
            query=query, db=db, organization_id=organization_id, top_k=top_k,
            use_semantic=use_semantic, use_keyword=use_keyword, doc_type=doc_type,
            department=department, document_filter=document_filter,
            boost_documents=boost_documents, query_embedding=query_embedding,
        )
        if not expand_neighbors or not results:
            return results
        started = time.perf_counter()
        top_ids = [r["chunk_id"] for r in results[:EXPAND_TOP]]
        neighbours = await vector_search_service.get_neighbors_batch(top_ids, db, organization_id)
        expanded: List[Dict[str, Any]] = []
        seen: set[str] = set()
        for result in results:
            if result["chunk_id"] not in seen:
                expanded.append({**result, "is_expanded_context": False})
                seen.add(result["chunk_id"])
            for neighbour in neighbours.get(result["chunk_id"], []):
                if neighbour["chunk_id"] in seen:
                    continue
                expanded.append({**neighbour, "is_expanded_context": True, "parent_chunk_id": result["chunk_id"]})
                seen.add(neighbour["chunk_id"])
        _stage("neighbour_expansion", started, added=len(expanded) - len(results))
        return expanded


hybrid_search_service = HybridSearchService()

__all__ = ["HybridSearchService", "hybrid_search_service"]
