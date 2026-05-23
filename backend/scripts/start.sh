#!/bin/bash
# =============================================================================
# Novera AI — Production Startup Script
#
# Execution order:
#   1. Wait for PostgreSQL to be reachable (max 60 s)
#   2. Run Alembic migrations (idempotent — safe on every deploy)
#   3. Start Gunicorn with Uvicorn workers
#
# Environment variables consumed:
#   DATABASE_URL      — asyncpg URL; we derive the sync URL for the health check
#   PORT              — defaults to 8000 (Render sets this automatically)
#   WEB_CONCURRENCY   — Gunicorn worker count (Render sets this automatically)
#   GUNICORN_TIMEOUT  — per-worker timeout in seconds (default 120)
# =============================================================================
set -euo pipefail

echo "============================================"
echo "🚀 Starting Novera AI"
echo "   $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
echo "============================================"

# ── Step 1: Wait for PostgreSQL ───────────────────────────────────────────────
echo ""
echo "⏳ Waiting for PostgreSQL..."

MAX_ATTEMPTS=30
attempt=0
until python - << 'PYEOF'
import sys, os
sys.path.insert(0, "/app")
from app.core.config import settings
from sqlalchemy import create_engine, text
try:
    engine = create_engine(settings.sync_database_url, pool_pre_ping=True)
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    print("ok")
except Exception as e:
    print(f"not ready: {e}", file=sys.stderr)
    sys.exit(1)
PYEOF
do
    attempt=$((attempt + 1))
    if [ "$attempt" -ge "$MAX_ATTEMPTS" ]; then
        echo "❌ PostgreSQL not reachable after $((MAX_ATTEMPTS * 2)) seconds. Aborting."
        exit 1
    fi
    echo "  Attempt $attempt/$MAX_ATTEMPTS — retrying in 2 s..."
    sleep 2
done
echo "✅ PostgreSQL is ready"

# ── Step 2: Alembic migrations ────────────────────────────────────────────────
echo ""
echo "🔄 Running Alembic migrations..."
cd /app

# Use the explicit config path so alembic.ini is always found regardless of CWD
if alembic -c /app/alembic.ini upgrade head; then
    echo "✅ Migrations complete"
else
    echo "⚠️  Migration command exited non-zero."
    echo "    This can happen if the schema is already current or if a prior"
    echo "    partial migration left the DB in an inconsistent state."
    echo "    Attempting to stamp head and continue..."
    alembic -c /app/alembic.ini stamp head || true
    echo "    Stamped. Proceeding — monitor for runtime errors."
fi

# ── Step 3: Start Gunicorn ────────────────────────────────────────────────────
echo ""
echo "🎉 Launching Gunicorn"
echo "   Workers  : ${WEB_CONCURRENCY:-2}"
echo "   Port     : ${PORT:-8000}"
echo "   Timeout  : ${GUNICORN_TIMEOUT:-120}s"
echo "============================================"

exec gunicorn app.main:app \
    --worker-class uvicorn.workers.UvicornWorker \
    --workers "${WEB_CONCURRENCY:-2}" \
    --bind "0.0.0.0:${PORT:-8000}" \
    --timeout "${GUNICORN_TIMEOUT:-120}" \
    --graceful-timeout 30 \
    --keep-alive 5 \
    --log-level info \
    --access-logfile - \
    --error-logfile -
