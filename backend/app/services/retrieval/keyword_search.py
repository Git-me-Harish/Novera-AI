"""Sparse (full-text) retrieval over the stored, GIN-indexed ``search_vector``.

The query ORs its terms: natural-language questions rarely share every word
with the passage that answers them (``plainto_tsquery`` ANDs them and missed
exact matches). Words of 4+ characters also match by prefix ("repay" finds
"repayment"); shorter ones match exactly, since a prefix on "an" or "pf"
matches far too much. Ranking is length-normalised so long chunks do not
win by size, and a section-title match (weight A) outranks a body match.
Errors roll back a SAVEPOINT, never the caller's whole transaction.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional
from uuid import UUID

from loguru import logger
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.retrieval.vector_search import _SELECT, _filters, _row_to_chunk

MAX_TERMS = 32
PREFIX_MIN_LENGTH = 4
# ts_rank_cd normalisation: 1 = divide by 1 + log(length), 32 = scale to 0..1.
RANK_NORMALIZATION = 1 | 32


def build_tsquery(query: str) -> str:
    """OR of the query's words; safe because only [A-Za-z0-9] survive."""
    terms, seen = [], set()
    for term in re.findall(r"[A-Za-z0-9]+", query or ""):
        key = term.lower()
        if key in seen:
            continue
        seen.add(key)
        terms.append(f"{key}:*" if len(key) >= PREFIX_MIN_LENGTH and not key.isdigit() else key)
        if len(terms) == MAX_TERMS:
            break
    return " | ".join(terms)


class KeywordSearchService:
    def __init__(self) -> None:
        self.default_top_k = 10

    async def search_keywords(
        self,
        query: str,
        db: AsyncSession,
        organization_id: UUID,
        top_k: Optional[int] = None,
        doc_type: Optional[str] = None,
        department: Optional[str] = None,
        document_filter: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        ts_query = build_tsquery(query)
        if not ts_query:
            return []
        where, params = _filters(organization_id, doc_type, department, None, document_filter)
        params.update({"ts_query": ts_query, "limit": top_k or self.default_top_k})
        sql = text(
            _SELECT
            + f""", ts_rank_cd(c.search_vector, q, {RANK_NORMALIZATION}) AS rank
            FROM chunks c
            JOIN documents d ON d.id = c.document_id,
                 to_tsquery('english', :ts_query) AS q
            WHERE {where} AND c.search_vector @@ q
            ORDER BY rank DESC
            LIMIT :limit
            """
        )
        try:
            async with db.begin_nested():
                rows = (await db.execute(sql, params)).mappings().all()
        except Exception as exc:
            logger.error(f"Keyword search failed: {type(exc).__name__}: {exc}")
            return []
        chunks = [_row_to_chunk(row, keyword_score=float(row["rank"])) for row in rows]
        logger.info(f"Keyword search: {len(chunks)} chunks")
        return chunks


keyword_search_service = KeywordSearchService()

__all__ = ["KeywordSearchService", "keyword_search_service", "build_tsquery"]
