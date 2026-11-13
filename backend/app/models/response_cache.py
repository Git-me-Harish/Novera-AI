"""Tenant-scoped semantic response cache records."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from pgvector.sqlalchemy import Vector
from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.db.session import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ResponseCacheEntry(Base):
    """A reusable grounded answer for one tenant and corpus snapshot."""

    __tablename__ = "response_cache_entries"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    organization_id = Column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    scope_key = Column(String(200), nullable=False)
    query_hash = Column(String(64), nullable=False)
    query_embedding = Column(Vector(1536), nullable=False)
    embedding_provider = Column(String(50), nullable=False)
    embedding_model = Column(String(255), nullable=False)
    embedding_dimensions = Column(Integer, nullable=False)
    corpus_fingerprint = Column(String(64), nullable=False)
    generation_model = Column(String(255), nullable=False)
    answer = Column(Text, nullable=False)
    sources = Column(JSONB, nullable=False, default=list)
    citations = Column(JSONB, nullable=False, default=list)
    entry_metadata = Column("metadata", JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    last_hit_at = Column(DateTime(timezone=True), nullable=True)
    hit_count = Column(Integer, nullable=False, default=0)

    __table_args__ = (
        Index("idx_response_cache_expires_at", "expires_at"),
        Index(
            "idx_response_cache_lookup",
            "organization_id",
            "scope_key",
            "corpus_fingerprint",
            "embedding_model",
            "embedding_dimensions",
            "expires_at",
        ),
        Index(
            "idx_response_cache_embedding_hnsw",
            "query_embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"query_embedding": "vector_cosine_ops"},
        ),
    )
