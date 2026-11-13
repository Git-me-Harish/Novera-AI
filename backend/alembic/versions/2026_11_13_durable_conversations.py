"""durable tenant-scoped conversations and messages

Chat history previously lived only in Redis with a 2-hour TTL and a 30-message
cap. These tables make it durable, searchable and tenant-scoped.

Revision ID: 20261113_conversations
Revises: 20261004_semantic_cache
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20261113_conversations"
down_revision = "20261004_semantic_cache"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    op.create_table(
        "conversations",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("title_source", sa.String(length=16), nullable=False, server_default="default"),
        sa.Column("is_pinned", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("pinned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_archived", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("message_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False,
                  server_default=sa.text("'{}'::jsonb")),
        sa.Column("context", postgresql.JSONB(astext_type=sa.Text()), nullable=False,
                  server_default=sa.text("'{}'::jsonb")),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("title_source IN ('default', 'auto', 'user')",
                           name="ck_conversations_title_source"),
        sa.CheckConstraint("message_count >= 0", name="ck_conversations_message_count"),
    )
    op.create_index(
        "ix_conversations_owner_recent", "conversations",
        ["organization_id", "user_id", "is_pinned", "last_message_at"],
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index(
        "ix_conversations_deleted_at", "conversations", ["deleted_at"],
        postgresql_where=sa.text("deleted_at IS NOT NULL"),
    )
    op.create_index(
        "ix_conversations_title_trgm", "conversations", ["title"],
        postgresql_using="gin", postgresql_ops={"title": "gin_trgm_ops"},
    )

    op.create_table(
        "conversation_messages",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("conversation_id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False,
                  server_default=sa.text("'{}'::jsonb")),
        sa.Column(
            "search_vector", postgresql.TSVECTOR(),
            sa.Computed("to_tsvector('simple', coalesce(content, ''))", persisted=True),
        ),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("conversation_id", "sequence", name="uq_conversation_messages_sequence"),
        sa.CheckConstraint("role IN ('user', 'assistant', 'system')",
                           name="ck_conversation_messages_role"),
    )
    op.create_index("ix_conversation_messages_search", "conversation_messages",
                    ["search_vector"], postgresql_using="gin")
    op.create_index("ix_conversation_messages_org", "conversation_messages", ["organization_id"])


def downgrade() -> None:
    op.drop_index("ix_conversation_messages_org", table_name="conversation_messages")
    op.drop_index("ix_conversation_messages_search", table_name="conversation_messages")
    op.drop_table("conversation_messages")
    op.drop_index("ix_conversations_title_trgm", table_name="conversations")
    op.drop_index("ix_conversations_deleted_at", table_name="conversations")
    op.drop_index("ix_conversations_owner_recent", table_name="conversations")
    op.drop_table("conversations")
