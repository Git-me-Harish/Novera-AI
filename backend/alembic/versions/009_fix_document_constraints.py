from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "009_fix_document_constraints"
down_revision = "008_fix_org_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # This migration must be safe against both the original schema and partially
    # migrated installations. Do not swallow DDL exceptions: PostgreSQL marks the
    # transaction as failed, so a later statement would fail with a misleading
    # InFailedSqlTransaction error.
    op.execute("DROP INDEX IF EXISTS ix_documents_file_hash")
    op.execute("ALTER TABLE documents DROP CONSTRAINT IF EXISTS documents_file_hash_key")
    op.execute("ALTER TABLE documents DROP CONSTRAINT IF EXISTS uq_documents_file_hash")

    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'uq_doc_hash_org'
            ) THEN
                ALTER TABLE documents
                    ADD CONSTRAINT uq_doc_hash_org UNIQUE (file_hash, organization_id);
            END IF;
        END $$;
        """
    )

    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'fk_documents_uploaded_by_users'
            ) THEN
                ALTER TABLE documents
                    ADD CONSTRAINT fk_documents_uploaded_by_users
                    FOREIGN KEY (uploaded_by) REFERENCES users(id) ON DELETE SET NULL;
            END IF;
        END $$;
        """
    )

    # Chunks table. IF NOT EXISTS keeps reruns safe after an interrupted deploy.
    op.execute(
        "ALTER TABLE chunks ADD COLUMN IF NOT EXISTS position INTEGER NOT NULL DEFAULT 0"
    )

    # Backfill position from chunk_index (they should be the same value)
    op.execute(
        "UPDATE chunks SET position = chunk_index WHERE position = 0 AND chunk_index > 0"
    )

    # Add index on (document_id, position)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_chunk_doc_position "
        "ON chunks (document_id, position)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_chunk_doc_position")
    op.execute("ALTER TABLE chunks DROP COLUMN IF EXISTS position")
    op.execute(
        "ALTER TABLE documents DROP CONSTRAINT IF EXISTS fk_documents_uploaded_by_users"
    )
    op.execute("ALTER TABLE documents DROP CONSTRAINT IF EXISTS uq_doc_hash_org")
    op.execute(
        "ALTER TABLE documents ADD CONSTRAINT documents_file_hash_key UNIQUE (file_hash)"
    )
