"""restore chunk retrieval indexes

Revision ID: fd1b01c3d607
Revises: 4e4d6fa1ea91
Create Date: 2026-10-02 16:37:00
"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "fd1b01c3d607"
down_revision: Union[str, Sequence[str], None] = "4e4d6fa1ea91"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Restore indexes removed by the ORM reconciliation migration."""

    # ------------------------------------------------------------------
    # Chunk metadata lookup
    # ------------------------------------------------------------------
    op.create_index(
        "idx_chunk_metadata_gin",
        "chunks",
        ["metadata"],
        unique=False,
        postgresql_using="gin",
    )

    # ------------------------------------------------------------------
    # Chunk type + document lookup
    # ------------------------------------------------------------------
    op.create_index(
        "idx_chunk_type_doc",
        "chunks",
        ["chunk_type", "document_id"],
        unique=False,
    )

    # ------------------------------------------------------------------
    # Embedding provenance lookup
    # ------------------------------------------------------------------
    op.create_index(
        "idx_chunks_embedding_contract",
        "chunks",
        [
            "embedding_provider",
            "embedding_model",
            "embedding_dimensions",
        ],
        unique=False,
    )

    # ------------------------------------------------------------------
    # Full-text/trigram content search
    # ------------------------------------------------------------------
    op.create_index(
        "idx_content_fts",
        "chunks",
        ["content"],
        unique=False,
        postgresql_using="gin",
        postgresql_ops={
            "content": "gin_trgm_ops",
        },
    )

    # ------------------------------------------------------------------
    # Document -> chunk lookup by chunk_index
    # ------------------------------------------------------------------
    op.create_index(
        "idx_doc_chunk",
        "chunks",
        ["document_id", "chunk_index"],
        unique=False,
    )

    # ------------------------------------------------------------------
    # pgvector cosine-similarity retrieval
    # ------------------------------------------------------------------
    op.create_index(
        "idx_embedding_cosine",
        "chunks",
        ["embedding"],
        unique=False,
        postgresql_using="ivfflat",
        postgresql_with={"lists": "100"},
        postgresql_ops={
            "embedding": "vector_cosine_ops",
        },
    )

    # ------------------------------------------------------------------
    # Existing single-column operational indexes
    # ------------------------------------------------------------------
    op.create_index(
        "ix_chunks_chunk_type",
        "chunks",
        ["chunk_type"],
        unique=False,
    )

    op.create_index(
        "ix_chunks_is_edited",
        "chunks",
        ["is_edited"],
        unique=False,
    )

    op.create_index(
        "ix_chunks_title",
        "chunks",
        ["title"],
        unique=False,
    )


def downgrade() -> None:
    """Remove restored indexes."""

    op.drop_index(
        "ix_chunks_is_edited",
        table_name="chunks",
    )

    op.drop_index(
        "ix_chunks_created_at",
        table_name="chunks",
    )

    op.drop_index(
        "ix_chunks_chunk_type",
        table_name="chunks",
    )

    op.drop_index(
        "idx_embedding_cosine",
        table_name="chunks",
    )

    op.drop_index(
        "idx_doc_chunk",
        table_name="chunks",
    )

    op.drop_index(
        "idx_content_fts",
        table_name="chunks",
    )

    op.drop_index(
        "idx_chunks_embedding_contract",
        table_name="chunks",
    )

    op.drop_index(
        "idx_chunk_type_doc",
        table_name="chunks",
    )

    op.drop_index(
        "idx_chunk_metadata_gin",
        table_name="chunks",
    )