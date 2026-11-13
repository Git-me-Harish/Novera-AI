"""
Database models for documents and chunks with pgvector support.

FIXES:
  1. file_hash unique constraint is now composite (file_hash, organization_id)
     — same file can exist in different organizations.
  2. uploaded_by has a proper ForeignKey to users.id.
  3. Chunk.position column added for deterministic ordering.
  4. Index on (document_id, position) for fast ordered chunk reads.
  5. lazy="selectin" on chunks changed to lazy="select" — selectin was
     loading ALL chunks on every Document query.
  6. All DateTime columns use timezone=True (TIMESTAMPTZ).
  7. ChunkEditHistory included for chunk audit/rollback (was accidentally
     dropped in a previous rewrite).
"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import relationship

from app.db.session import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Document(Base):
    """Metadata record for an uploaded document."""

    __tablename__ = "documents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)

    # Organisation scope
    organization_id = Column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    organization = relationship("Organization", back_populates="documents")

    # File metadata
    filename = Column(String(255), nullable=False, index=True)
    original_filename = Column(String(255), nullable=False)
    file_path = Column(String(512), nullable=False)
    file_size_bytes = Column(Integer, nullable=False)
    file_hash = Column(String(64), nullable=False, index=True)

    # Classification
    doc_type = Column(String(50), nullable=False, index=True)
    department = Column(String(100), index=True)

    # Document details
    total_pages = Column(Integer, default=0)
    total_chunks = Column(Integer, default=0)
    has_tables = Column(Boolean, default=False)
    has_images = Column(Boolean, default=False)

    # Processing status
    status = Column(String(20), nullable=False, default="pending", index=True)
    processing_error = Column(Text, nullable=True)

    # Timestamps — all TIMESTAMPTZ
    upload_date = Column(DateTime(timezone=True), nullable=False, default=_utcnow, index=True)
    processed_date = Column(DateTime(timezone=True), nullable=True)
    last_accessed = Column(DateTime(timezone=True), nullable=True)

    # FIX: proper FK to users.id with SET NULL on delete
    uploaded_by = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # JSONB metadata — attribute name differs from column name to avoid conflicts
    doc_metadata = Column("metadata", JSONB, nullable=False, default=dict)

    # FIX: lazy="select" (was "selectin" which loaded ALL chunks on every Document query)
    chunks = relationship(
        "Chunk",
        back_populates="document",
        cascade="all, delete-orphan",
        lazy="select",
        order_by="Chunk.position",
    )

    __table_args__ = (
        # FIX: composite unique — same file can exist in different orgs
        UniqueConstraint("file_hash", "organization_id", name="uq_doc_hash_org"),
        Index("idx_doc_type_dept", "doc_type", "department"),
        Index("idx_status_upload", "status", "upload_date"),
        Index("idx_metadata_gin", "metadata", postgresql_using="gin"),
        Index("idx_org_status", "organization_id", "status"),
    )

    def __repr__(self) -> str:
        return f"<Document(id={self.id}, filename={self.filename}, status={self.status})>"


class Chunk(Base):
    """A single text chunk extracted from a document, with its embedding."""

    __tablename__ = "chunks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    document_id = Column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    document = relationship("Document", back_populates="chunks")

    # Content. These names are the canonical database contract used by the
    # ingestion and retrieval SQL. Keep them aligned with the initial schema
    # rather than introducing ORM-only aliases.
    content = Column(Text, nullable=False)
    title = Column(String(500), nullable=True)
    content_length = Column(Integer, nullable=False, default=0)
    token_count = Column(Integer, nullable=False, default=0)
    chunk_type = Column(String(50), nullable=False, default="text")
    page_numbers = Column(ARRAY(Integer), nullable=False, default=list)
    section_title = Column(String(512), nullable=True)
    preceding_context = Column(Text, nullable=True)

    # FIX: position column for deterministic ordering within a document
    position = Column(Integer, nullable=False, default=0)
    chunk_index = Column(Integer, nullable=False, default=0)

    # Vector embedding (pgvector)
    embedding = Column(Vector(1536), nullable=True)
    # Embedding provenance. Rows without matching provenance are deliberately
    # excluded from dense retrieval until they are re-embedded.
    embedding_provider = Column(String(50), nullable=True)
    embedding_model = Column(String(255), nullable=True)
    embedding_dimensions = Column(Integer, nullable=True)
    embedding_task = Column(String(50), nullable=True)

    # Edit support
    is_edited = Column(Boolean, default=False, nullable=False)
    edit_count = Column(Integer, default=0, nullable=False)
    original_content = Column(Text, nullable=True)
    edited_at = Column(DateTime(timezone=True), nullable=True)
    edited_by = Column(UUID(as_uuid=True), nullable=True)

    # JSONB metadata
    chunk_metadata = Column("metadata", JSONB, nullable=False, default=dict)

    __table_args__ = (
        # Ordered chunk retrieval
        Index("idx_chunk_doc_position", "document_id", "position"),

        # Page-based retrieval
        Index("idx_chunk_page", "document_id", "page_numbers"),

        # Chunk type filtering
        Index("idx_chunk_type", "chunk_type"),

        # Metadata filtering
        Index(
            "idx_chunk_metadata_gin",
            "metadata",
            postgresql_using="gin",
        ),

        # Combined chunk/document lookup
        Index(
            "idx_chunk_type_doc",
            "chunk_type",
            "document_id",
        ),

        # Embedding provenance lookup
        Index(
            "idx_chunks_embedding_contract",
            "embedding_provider",
            "embedding_model",
            "embedding_dimensions",
        ),

        # Text search
        Index(
            "idx_content_fts",
            "content",
            postgresql_using="gin",
            postgresql_ops={"content": "gin_trgm_ops"},
        ),

        # Document chunk ordering lookup
        Index(
            "idx_doc_chunk",
            "document_id",
            "chunk_index",
        ),

        # Vector similarity retrieval
        Index(
            "idx_embedding_cosine",
            "embedding",
            postgresql_using="ivfflat",
            postgresql_with={"lists": 100},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),

        # Existing single-column indexes
        Index("ix_chunks_chunk_type", "chunk_type"),
        Index("ix_chunks_is_edited", "is_edited"),
        Index("ix_chunks_title", "title"),
    )

    def __repr__(self) -> str:
        return f"<Chunk(id={self.id}, doc={self.document_id}, pos={self.position})>"

    def to_dict(self, include_edit_info: bool = False) -> dict:
        result = {
            "id": str(self.id),
            "document_id": str(self.document_id),
            "content": self.content,
            "title": self.title,
            "chunk_type": self.chunk_type,
            "content_length": self.content_length,
            "token_count": self.token_count,
            "position": self.position,
            "page_numbers": self.page_numbers,
            "section_title": self.section_title,
            "chunk_index": self.chunk_index,
            "is_edited": self.is_edited,
            "edit_count": self.edit_count,
            "metadata": self.chunk_metadata or {},
            "embedding_provider": self.embedding_provider,
            "embedding_model": self.embedding_model,
            "embedding_dimensions": self.embedding_dimensions,
            "embedding_task": self.embedding_task,
        }
        if include_edit_info:
            result.update({
                "edited_at": self.edited_at.isoformat() if self.edited_at else None,
                "edited_by": str(self.edited_by) if self.edited_by else None,
            })
        return result


class ChunkEditHistory(Base):
    """Track the full edit history of a chunk for audit and rollback."""

    __tablename__ = "chunk_edit_history"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    chunk_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    document_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    edited_by = Column(UUID(as_uuid=True), nullable=False)
    # FIX: timezone=True — consistent with all other DateTime columns
    edited_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    old_content = Column(Text, nullable=False)
    new_content = Column(Text, nullable=False)
    change_summary = Column(String(500), nullable=True)

    # attribute name != column name to avoid JSONB reserved word clash
    edit_metadata = Column("metadata", JSONB, nullable=False, default=dict)

    __table_args__ = (
        Index("idx_chunk_edit_history_chunk", "chunk_id"),
        Index("idx_chunk_edit_history_doc", "document_id"),
        Index("idx_chunk_edit_history_user", "edited_by"),
    )

    def __repr__(self) -> str:
        return f"<ChunkEditHistory(chunk_id={self.chunk_id}, edited_at={self.edited_at})>"


__all__ = ["Document", "Chunk", "ChunkEditHistory"]
