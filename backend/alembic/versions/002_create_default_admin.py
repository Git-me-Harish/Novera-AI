"""create default admin user

Revision ID: 002_create_default_admin
Revises: 4d6894fa45b4
Create Date: 2024-01-15 10:00:00.000000

"""
from alembic import op, context
import sqlalchemy as sa
import os
from sqlalchemy.sql import table, column
from datetime import datetime
from uuid import uuid4

# revision identifiers, used by Alembic.
revision = '002_create_default_admin'
down_revision = '4d6894fa45b4'
branch_labels = None
depends_on = None

# ── Canonical admin credentials ───────────────────────────────────────────────
# The email is the unique identifier used by both upgrade() and downgrade().
# We also accept the legacy mentanova email so existing deployments that
# already ran this migration don't get a duplicate row on the next run.
_ADMIN_EMAIL = "admin@novera.ai"
_LEGACY_EMAIL = "admin@mentanova.com"   # left over from old branding


def upgrade():
    """Create default admin user if not exists."""
    if context.is_offline_mode():
        # Data-dependent user creation cannot be rendered safely as static SQL.
        # It still runs normally during online deployment.
        return
    from app.core.security import get_password_hash

    admin_email = os.getenv("DEFAULT_ADMIN_EMAIL", _ADMIN_EMAIL).strip()
    admin_password = os.getenv("DEFAULT_ADMIN_PASSWORD", "").strip()
    if not admin_password:
        raise RuntimeError(
            "DEFAULT_ADMIN_PASSWORD must be set before creating the initial admin account"
        )

    users_table = table(
        'users',
        column('id', sa.dialects.postgresql.UUID),
        column('email', sa.String),
        column('username', sa.String),
        column('hashed_password', sa.String),
        column('full_name', sa.String),
        column('role', sa.String),
        column('is_active', sa.Boolean),
        column('is_verified', sa.Boolean),
        column('created_at', sa.DateTime),
        column('updated_at', sa.DateTime),
        column('preferences', sa.dialects.postgresql.JSONB),
        column('metadata', sa.dialects.postgresql.JSONB),
    )

    connection = op.get_bind()

    # Check for either the new OR the legacy admin email so we never duplicate
    result = connection.execute(
        sa.text(
            "SELECT COUNT(*) FROM users "
            "WHERE email IN (:new_email, :legacy_email)"
        ),
        {"new_email": admin_email, "legacy_email": _LEGACY_EMAIL},
    ).scalar()

    if result == 0:
        admin_id = uuid4()
        hashed_password = get_password_hash(admin_password)

        op.execute(
            users_table.insert().values(
                id=admin_id,
                email=admin_email,
                username='admin',
                hashed_password=hashed_password,
                full_name='System Administrator',
                role='admin',
                is_active=True,
                is_verified=True,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
                preferences={},
                metadata={'created_by': 'system', 'is_default_admin': True}
            )
        )

        print("\n" + "=" * 60)
        print("DEFAULT ADMIN USER CREATED")
        print("=" * 60)
        print(f"Email:    {admin_email}")
        print("=" * 60)
        print("IMPORTANT: rotate the initial admin password after first login")
        print("=" * 60 + "\n")
    else:
        print("\nAdmin user already exists - skipping creation.\n")


def downgrade():
    """Remove default admin user (both email variants)."""
    if context.is_offline_mode():
        return
    admin_email = os.getenv("DEFAULT_ADMIN_EMAIL", _ADMIN_EMAIL).strip()
    connection = op.get_bind()
    connection.execute(
        sa.text(
            "DELETE FROM users "
            "WHERE email IN (:new_email, :legacy_email) "
            "AND metadata->>'is_default_admin' = 'true'"
        ),
        {"new_email": admin_email, "legacy_email": _LEGACY_EMAIL},
    )
    print("Default admin user removed")
