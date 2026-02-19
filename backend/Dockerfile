# =========================
# 1️⃣ Frontend build stage
# =========================
FROM node:20-alpine AS frontend-builder

WORKDIR /frontend

COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install --legacy-peer-deps

COPY frontend/ .
RUN npm run build


# =========================
# 2️⃣ Backend + API stage
# =========================
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY backend/requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend source (includes alembic)
COPY backend/ backend/

# Copy frontend build into backend/static
COPY --from=frontend-builder /frontend/dist backend/static

# Ensure Python can import backend.app
ENV PYTHONPATH=/app/backend

# Expose FastAPI port
EXPOSE 8000

# Production command: run migrations then start server
CMD ["sh", "-c", "alembic -c backend/alembic.ini upgrade head && uvicorn backend.app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
