# Copyright 2026 VibeCast Team
# Multi-stage Docker build for Cloud Run deployment

FROM python:3.12-slim AS base

# Security: run as non-root user (Day 4, Pillar 1)
RUN groupadd -r vibecast && useradd -r -g vibecast vibecast

WORKDIR /app

# Install system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv for fast dependency management
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy dependency files first for layer caching
COPY pyproject.toml uv.lock ./

# Install Python dependencies (frozen for reproducible builds)
RUN uv sync --frozen --no-dev --no-editable

# Copy application code
COPY app/ ./app/
COPY .env.example ./.env.example

# Switch to non-root user
USER vibecast

# Cloud Run uses PORT env var (default 8080)
ENV PORT=8080
ENV PYTHONUNBUFFERED=1
ENV GOOGLE_GENAI_USE_VERTEXAI=False

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:${PORT}/health || exit 1

# Start the ADK web server
CMD ["uv", "run", "adk", "web", "--port", "8080", "--host", "0.0.0.0"]
