
# =========================
# 1️⃣ Frontend build stage
# =========================
FROM node:20-alpine AS frontend-builder

WORKDIR /frontend

COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install

COPY frontend/ .
RUN npm run build


# =========================
# 2️⃣ Backend + API stage
# =========================
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies (optional but recommended)
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY backend/requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend source (includes alembic + alembic.ini)
COPY backend/ backend/

# Copy built frontend into backend static folder
COPY --from=frontend-builder /frontend/dist backend/static

# Ensure Python can import backend.app
ENV PYTHONPATH=/app/backend

# Render expects port binding
EXPOSE 8000

# ✅ RUN MIGRATIONS FIRST, THEN START SERVER
CMD ["sh", "-c", "alembic -c backend/alembic.ini upgrade head && uvicorn backend.app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
