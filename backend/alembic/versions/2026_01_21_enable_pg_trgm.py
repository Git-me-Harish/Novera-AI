"""enable pg_trgm extension

Revision ID: enable_pg_trgm
Revises: enable_pgvector
Create Date: 2026-01-21
"""

from alembic import op
from typing import Sequence, Union

revision: str = "enable_pg_trgm"
down_revision: Union[str, Sequence[str], None] = "enable_pgvector"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")


def downgrade() -> None:
    op.execute("DROP EXTENSION IF EXISTS pg_trgm")
