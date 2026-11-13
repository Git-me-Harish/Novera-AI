"""010_timezone_aware_timestamps.py

Convert all naive DateTime columns to timezone-aware (TIMESTAMPTZ) so that
comparisons with timezone.utc datetimes from Python don't silently fail or
produce wrong results.

Affected tables: users, refresh_tokens, password_reset_tokens, email_verification_tokens
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "010_timezone_aware_timestamps"
down_revision = "009_fix_document_constraints"
branch_labels = None
depends_on = None

# Tables and columns to convert
_CONVERSIONS = {
    "users": [
        "created_at", "updated_at", "last_login",
    ],
    "refresh_tokens": [
        "expires_at", "created_at",
    ],
    "password_reset_tokens": [
        "expires_at", "created_at",
    ],
    "email_verification_tokens": [
        "expires_at", "created_at",
    ],
    "documents": [
        "upload_date", "processed_date", "last_accessed",
    ],
    "chunks": [
        "edited_at",
    ],
}


def upgrade() -> None:
    for table, columns in _CONVERSIONS.items():
        for col in columns:
            op.execute(
                f"""
                DO $$
                BEGIN
                    IF to_regclass('public.{table}') IS NOT NULL
                       AND EXISTS (
                           SELECT 1 FROM information_schema.columns
                           WHERE table_schema = 'public'
                             AND table_name = '{table}'
                             AND column_name = '{col}'
                       ) THEN
                        EXECUTE 'ALTER TABLE public.{table} '
                                || 'ALTER COLUMN {col} TYPE TIMESTAMPTZ '
                                || 'USING {col} AT TIME ZONE ''UTC''';
                    END IF;
                END $$;
                """
            )


def downgrade() -> None:
    for table, columns in _CONVERSIONS.items():
        for col in columns:
            op.execute(
                f"""
                DO $$
                BEGIN
                    IF to_regclass('public.{table}') IS NOT NULL
                       AND EXISTS (
                           SELECT 1 FROM information_schema.columns
                           WHERE table_schema = 'public'
                             AND table_name = '{table}'
                             AND column_name = '{col}'
                       ) THEN
                        EXECUTE 'ALTER TABLE public.{table} '
                                || 'ALTER COLUMN {col} TYPE TIMESTAMP '
                                || 'USING {col} AT TIME ZONE ''UTC''';
                    END IF;
                END $$;
                """
            )
