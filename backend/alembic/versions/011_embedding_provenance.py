"""011_embedding_provenance

Persist the provider/model contract for every stored vector. Existing rows are
left unlabelled and are excluded from dense retrieval until re-embedded; this
is safer than guessing their vector space.
"""
from __future__ import annotations

from alembic import op

revision = "011_embedding_provenance"
down_revision = "010_timezone_aware_timestamps"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE chunks ADD COLUMN IF NOT EXISTS embedding_provider VARCHAR(50)")
    op.execute("ALTER TABLE chunks ADD COLUMN IF NOT EXISTS embedding_model VARCHAR(255)")
    op.execute("ALTER TABLE chunks ADD COLUMN IF NOT EXISTS embedding_dimensions INTEGER")
    op.execute("ALTER TABLE chunks ADD COLUMN IF NOT EXISTS embedding_task VARCHAR(50)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_chunks_embedding_contract "
        "ON chunks (embedding_provider, embedding_model, embedding_dimensions)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_chunks_embedding_contract")
    op.execute("ALTER TABLE chunks DROP COLUMN IF EXISTS embedding_task")
    op.execute("ALTER TABLE chunks DROP COLUMN IF EXISTS embedding_dimensions")
    op.execute("ALTER TABLE chunks DROP COLUMN IF EXISTS embedding_model")
    op.execute("ALTER TABLE chunks DROP COLUMN IF EXISTS embedding_provider")
