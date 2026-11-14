"""Retrieval indexes: HNSW vectors, stored weighted full-text vector.

* ``idx_embedding_cosine`` was IVFFlat with lists=100, built when the table
  held a few hundred rows. IVFFlat clusters are fixed at build time and the
  default probes=1 scans one of 100 lists, so once the planner starts using
  the index, recall collapses. HNSW needs no training data, keeps recall as
  the table grows and, with pgvector >= 0.8 iterative scans, keeps returning
  rows when tenant and model filters remove candidates.
* Keyword search recomputed ``to_tsvector(content)`` for every row on every
  query; the only text index (trigram on ``content``) could not serve that
  query and no code used it. ``search_vector`` is computed once on write:
  the section path is weighted above the body so a heading match ranks a
  chunk higher, and it has a GIN index.

Indexes are built CONCURRENTLY so a large production table stays writable.

Revision ID: 20261115_retrieval
Revises: 20261114_tenancy
"""
from alembic import op

revision = "20261115_retrieval"
down_revision = "20261114_tenancy"
branch_labels = None
depends_on = None

SEARCH_VECTOR = (
    "setweight(to_tsvector('english', coalesce(section_title, '')), 'A') || "
    "setweight(to_tsvector('english', coalesce(content, '')), 'B')"
)


def upgrade() -> None:
    op.execute(f"ALTER TABLE chunks ADD COLUMN IF NOT EXISTS search_vector tsvector GENERATED ALWAYS AS ({SEARCH_VECTOR}) STORED")
    with op.get_context().autocommit_block():
        op.execute("CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_chunks_search_vector ON chunks USING gin (search_vector)")
        op.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_chunks_embedding_hnsw ON chunks "
            "USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64)"
        )
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_embedding_cosine")
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_content_fts")


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_embedding_cosine ON chunks "
            "USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)"
        )
        op.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_content_fts ON chunks USING gin (content gin_trgm_ops)"
        )
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_chunks_embedding_hnsw")
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_chunks_search_vector")
    op.execute("ALTER TABLE chunks DROP COLUMN IF EXISTS search_vector")
