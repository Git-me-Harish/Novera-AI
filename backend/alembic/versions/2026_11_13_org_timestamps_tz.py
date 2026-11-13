"""timezone-aware organization and customization timestamps

Migration 010 converted most timestamps to timestamptz but missed these two
tables. Code now writes timezone-aware values everywhere; asyncpg rejects
aware values for ``timestamp without time zone`` columns. Existing values were
written as UTC, so they are interpreted as UTC.

Revision ID: 20261113_org_tz
Revises: 20261113_conversations
"""

from alembic import op
import sqlalchemy as sa


revision = "20261113_org_tz"
down_revision = "20261113_conversations"
branch_labels = None
depends_on = None

_COLUMNS = [
    ("organizations", "created_at"),
    ("organizations", "updated_at"),
    ("organization_customizations", "created_at"),
    ("organization_customizations", "updated_at"),
]


def upgrade() -> None:
    for table, column in _COLUMNS:
        op.alter_column(
            table, column,
            type_=sa.DateTime(timezone=True),
            existing_type=sa.DateTime(),
            existing_nullable=False,
            postgresql_using=f"{column} AT TIME ZONE 'UTC'",
        )


def downgrade() -> None:
    for table, column in _COLUMNS:
        op.alter_column(
            table, column,
            type_=sa.DateTime(),
            existing_type=sa.DateTime(timezone=True),
            existing_nullable=False,
            postgresql_using=f"{column} AT TIME ZONE 'UTC'",
        )
