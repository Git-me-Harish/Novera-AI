"""enable pgvector extension

Revision ID: enable_pgvector
Revises:
Create Date: 2026-01-21
"""

from alembic import op
from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = "enable_pgvector"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")


def downgrade() -> None:
    op.execute("DROP EXTENSION IF EXISTS vector")
