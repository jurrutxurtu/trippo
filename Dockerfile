# syntax=docker/dockerfile:1

# -----------------------------------------------------------------------------
# Stage 1: Build Frontend SPA
# -----------------------------------------------------------------------------
FROM node:22-alpine AS frontend-builder
WORKDIR /build

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build

# -----------------------------------------------------------------------------
# Stage 2: Runtime Backend
# -----------------------------------------------------------------------------
FROM python:3.12-slim-bookworm AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TRIPPO_WORKSPACE=/data/capsules \
    TRIPPO_STATIC_DIR=/app/static \
    TRIPPO_HEADLESS=1

# Install uv for fast package installation
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Install system dependencies (curl for healthcheck, ca-certificates)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Copy backend package specification and source code
COPY backend/pyproject.toml ./
COPY backend/trippo ./trippo

# Install backend dependencies without virtualenv into system python
RUN uv pip install --system --no-cache -e .

# Copy compiled frontend from Stage 1 into static serving directory
COPY --from=frontend-builder /build/dist /app/static

# Ensure data directory exists
RUN mkdir -p /data/capsules

EXPOSE 8787

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD curl -f http://127.0.0.1:8787/api/health || exit 1

CMD ["python", "-m", "uvicorn", "trippo.api.app:app", "--host", "0.0.0.0", "--port", "8787"]
