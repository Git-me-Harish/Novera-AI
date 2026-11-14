"""Dense retrieval with pgvector.

* Ordered by the distance operator itself (``embedding <=> :q``), the only
  form an HNSW index can serve; ordering by a computed similarity column
  forced an exact scan of every candidate row.
* ``hnsw.iterative_scan`` (pgvector >= 0.8) keeps scanning the graph when
  tenant, status and model filters remove candidates, so a small tenant in
  a large table still gets its k nearest chunks. ``ef_search`` sets the
  recall/latency trade-off.
* Only vectors from the configured embedding model are compared.
* Errors roll back a SAVEPOINT, never the caller's whole transaction.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence
from uuid import UUID

from loguru import logger
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.services.embedding.embedding_service import embedding_service


def _as_dict(value: Any) -> dict:
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    try:
        return dict(value)
    except (TypeError, ValueError):
        return {}


def _vector_literal(embedding: Sequence[float]) -> str:
    return "[" + ",".join(repr(float(v)) for v in embedding) + "]"


def _row_to_chunk(row, **extra) -> Dict[str, Any]:
    chunk_metadata = _as_dict(row["chunk_metadata"])
    chunk = {
        "chunk_id": str(row["chunk_id"]),
        "id": str(row["chunk_id"]),
        "document_id": str(row["document_id"]),
        "document_name": row["filename"],
        "content": row["content"],
        "chunk_type": row["chunk_type"],
        "chunk_index": row["chunk_index"],
        "page_numbers": row["page_numbers"],
        "section_title": row["section_title"],
        "token_count": row["token_count"],
        "chunk_metadata": chunk_metadata,
        "metadata": {
            "document_title": row["filename"],
            "doc_type": row["doc_type"],
            "department": row["department"],
            **chunk_metadata,
        },
    }
    chunk.update(extra)
    return chunk


_SELECT = """
    SELECT c.id AS chunk_id, c.document_id, c.content, c.chunk_type, c.chunk_index,
           c.page_numbers, c.section_title, c.token_count, c.metadata AS chunk_metadata,
           d.filename, d.doc_type, d.department
"""


def _filters(
    organization_id: UUID,
    doc_type: Optional[str],
    department: Optional[str],
    document_ids: Optional[List[UUID]],
    document_filter: Optional[List[str]],
) -> tuple[str, dict]:
    clauses = ["d.status = 'completed'", "d.organization_id = :organization_id"]
    params: dict[str, Any] = {"organization_id": organization_id}
    if doc_type:
        clauses.append("d.doc_type = :doc_type")
        params["doc_type"] = doc_type
    if department:
        clauses.append("d.department = :department")
        params["department"] = department
    if document_ids:
        clauses.append("d.id = ANY(:document_ids)")
        params["document_ids"] = list(document_ids)
    if document_filter:
        names = []
        for i, name in enumerate(document_filter):
            names.append(f"d.filename ILIKE :doc_filter_{i}")
            params[f"doc_filter_{i}"] = f"%{name}%"
        clauses.append("(" + " OR ".join(names) + ")")
    return " AND ".join(clauses), params


class VectorSearchService:
    def __init__(self) -> None:
        self.top_k = settings.retrieval_top_k
        self.similarity_threshold = settings.similarity_threshold
        self._iterative_scan: Optional[bool] = None  # probed once

    async def _tune_hnsw(self, db: AsyncSession) -> None:
        """Per-transaction HNSW settings; probed once for older pgvector."""
        await db.execute(text(f"SET LOCAL hnsw.ef_search = {int(settings.hnsw_ef_search)}"))
        if self._iterative_scan is False:
            return
        try:
            async with db.begin_nested():
                await db.execute(text("SET LOCAL hnsw.iterative_scan = relaxed_order"))
            self._iterative_scan = True
        except Exception:
            self._iterative_scan = False
            logger.warning("pgvector < 0.8: filtered vector searches may return fewer than k rows")

    async def search_similar_chunks(
        self,
        query_embedding: List[float],
        db: AsyncSession,
        organization_id: UUID,
        top_k: Optional[int] = None,
        doc_type: Optional[str] = None,
        department: Optional[str] = None,
        document_ids: Optional[List[UUID]] = None,
        document_filter: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        k = top_k or self.top_k
        where, params = _filters(organization_id, doc_type, department, document_ids, document_filter)
        params.update({
            "embedding": _vector_literal(query_embedding),
            "embedding_provider": embedding_service.provider,
            "embedding_model": embedding_service.model_name,
            "embedding_dimensions": embedding_service.dimensions,
            "limit": k,
        })
        sql = text(
            _SELECT
            + """, 1 - (c.embedding <=> CAST(:embedding AS vector)) AS similarity
            FROM chunks c JOIN documents d ON d.id = c.document_id
            WHERE """ + where + """
              AND c.embedding IS NOT NULL
              AND c.embedding_provider = :embedding_provider
              AND c.embedding_model = :embedding_model
              AND c.embedding_dimensions = :embedding_dimensions
            ORDER BY c.embedding <=> CAST(:embedding AS vector)
            LIMIT :limit
            """
        )
        try:
            async with db.begin_nested():
                await self._tune_hnsw(db)
                rows = (await db.execute(sql, params)).mappings().all()
        except Exception as exc:
            logger.error(f"Vector search failed: {type(exc).__name__}: {exc}")
            return []
        # relaxed_order may return near-ties slightly out of order.
        chunks = [
            _row_to_chunk(row, similarity_score=float(row["similarity"]))
            for row in rows
            if float(row["similarity"]) >= self.similarity_threshold
        ]
        chunks.sort(key=lambda c: c["similarity_score"], reverse=True)
        logger.info(f"Vector search: {len(chunks)} chunks above {self.similarity_threshold}")
        return chunks

    async def search_by_document(
        self,
        query_embedding: List[float],
        document_id: UUID,
        db: AsyncSession,
        organization_id: UUID,
        top_k: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        return await self.search_similar_chunks(
            query_embedding=query_embedding, db=db, organization_id=organization_id,
            top_k=top_k, document_ids=[document_id],
        )

    async def get_neighbors_batch(
        self,
        chunk_ids: List[str],
        db: AsyncSession,
        organization_id: UUID,
        *,
        span: int = 1,
        same_section: bool = True,
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Adjacent chunks for many hits in one query.

        A section split across chunks continues in its neighbour; a
        neighbour from a different section is unrelated text, so by default
        only neighbours within the same section are returned.
        """
        if not chunk_ids:
            return {}
        sql = text(
            _SELECT
            + """, t.id AS target_id
            FROM chunks t
            JOIN documents d ON d.id = t.document_id
            JOIN chunks c ON c.document_id = t.document_id
                         AND c.chunk_index BETWEEN t.chunk_index - :span AND t.chunk_index + :span
                         AND c.id <> t.id
            WHERE t.id = ANY(:ids) AND d.organization_id = :organization_id AND d.status = 'completed'
            """
            + ("AND c.section_title IS NOT DISTINCT FROM t.section_title " if same_section else "")
            + "ORDER BY t.id, c.chunk_index"
        )
        params = {"ids": [UUID(i) for i in chunk_ids], "organization_id": organization_id, "span": span}
        try:
            async with db.begin_nested():
                rows = (await db.execute(sql, params)).mappings().all()
        except Exception as exc:
            logger.error(f"Neighbour lookup failed: {type(exc).__name__}: {exc}")
            return {}
        neighbours: Dict[str, List[Dict[str, Any]]] = {}
        for row in rows:
            neighbours.setdefault(str(row["target_id"]), []).append(_row_to_chunk(row))
        return neighbours

    async def get_chunk_neighbors(
        self,
        chunk_id: UUID,
        db: AsyncSession,
        organization_id: UUID,
        n_before: int = 1,
        n_after: int = 1,
    ) -> List[Dict[str, Any]]:
        """Kept for callers of the old API: the chunk and its neighbours, in order."""
        span = max(n_before, n_after)
        neighbours = (await self.get_neighbors_batch(
            [str(chunk_id)], db, organization_id, span=span, same_section=False
        )).get(str(chunk_id), [])
        sql = text(_SELECT + """ FROM chunks c JOIN documents d ON d.id = c.document_id
                   WHERE c.id = :id AND d.organization_id = :organization_id""")
        async with db.begin_nested():
            target = (await db.execute(sql, {"id": chunk_id, "organization_id": organization_id})).mappings().first()
        if target is None:
            return []
        rows = [_row_to_chunk(target, is_target=True)] + [{**n, "is_target": False} for n in neighbours]
        return sorted(rows, key=lambda c: c["chunk_index"])


vector_search_service = VectorSearchService()

__all__ = ["VectorSearchService", "vector_search_service"]
