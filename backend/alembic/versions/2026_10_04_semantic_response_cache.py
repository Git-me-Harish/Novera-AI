"""add tenant-scoped semantic response cache

Revision ID: 20261004_semantic_cache
Revises: fd1b01c3d607
"""

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql


revision = "20261004_semantic_cache"
down_revision = "fd1b01c3d607"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "response_cache_entries",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("scope_key", sa.String(length=200), nullable=False),
        sa.Column("query_hash", sa.String(length=64), nullable=False),
        sa.Column("query_embedding", Vector(1536), nullable=False),
        sa.Column("embedding_provider", sa.String(length=50), nullable=False),
        sa.Column("embedding_model", sa.String(length=255), nullable=False),
        sa.Column("embedding_dimensions", sa.Integer(), nullable=False),
        sa.Column("corpus_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("generation_model", sa.String(length=255), nullable=False),
        sa.Column("answer", sa.Text(), nullable=False),
        sa.Column("sources", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("citations", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_hit_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("hit_count", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_response_cache_lookup", "response_cache_entries", [
        "organization_id", "scope_key", "corpus_fingerprint", "embedding_model",
        "embedding_dimensions", "expires_at",
    ])
    op.create_index("idx_response_cache_expires_at", "response_cache_entries", ["expires_at"])
    op.execute(
        "CREATE INDEX idx_response_cache_embedding_hnsw "
        "ON response_cache_entries USING hnsw (query_embedding vector_cosine_ops) "
        "WITH (m = 16, ef_construction = 64)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_response_cache_embedding_hnsw")
    op.drop_index("idx_response_cache_expires_at", table_name="response_cache_entries")
    op.drop_index("idx_response_cache_lookup", table_name="response_cache_entries")
    op.drop_table("response_cache_entries")
