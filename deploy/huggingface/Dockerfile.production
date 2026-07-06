# =============================================================================
# FASHIONISTAR — Production Dockerfile (Hugging Face Spaces)
# =============================================================================
# Target:  Hugging Face Spaces (Docker SDK — linux/amd64)
# Port:    7860 (HF mandatory) | UID: 1000 (HF mandatory)
#
# HF Spaces Dev Mode requirements (PRO plan):
#   ✓ bash, git, git-lfs, curl, wget, procps installed
#   ✓ /app owned by UID 1000
#   ✓ CMD instruction present
#   ✓ Debian-based image (python:3.13-slim ✓)
# =============================================================================

# ── Stage 1: uv binary ───────────────────────────────────────────────────────
# Versions are hardcoded (NOT ARG) because HF Spaces injects Space secrets as
# Docker build args, overriding ARG defaults and causing build failures.
FROM ghcr.io/astral-sh/uv:0.8.22 AS uvbin

# ── Stage 2: dependency builder ──────────────────────────────────────────────
FROM python:3.13-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv

# Build-time system dependencies (libpq-dev for psycopg compilation)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY --from=uvbin /uv /uvx /bin/

WORKDIR /app

# Copy dependency manifests first (layer caching — only rebuilds if these change)
COPY pyproject.toml uv.lock ./

# Install production dependencies into /opt/venv
RUN uv sync --frozen --no-dev --no-editable --no-install-project

# ── Stage 3: production runtime ───────────────────────────────────────────────
FROM python:3.13-slim AS runner

# Runtime environment
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH" \
    DJANGO_SETTINGS_MODULE=backend.config.production \
    WORKING_ENVIRONMENT=production \
    PORT=7860 \
    OLLAMA_ENABLED=True \
    UVICORN_WS=auto \
    GUNICORN_WORKERS=3 \
    GUNICORN_TIMEOUT=900 \
    GUNICORN_KEEPALIVE=900 \
    GUNICORN_MAX_REQUESTS=1000 \
    GUNICORN_MAX_REQUESTS_JITTER=100 \
    GUNICORN_LOG_LEVEL=info

# Runtime system dependencies
# IMPORTANT: bash, git, git-lfs, wget, procps are REQUIRED for HF Spaces Dev Mode (PRO plan).
# Without them, Dev Mode injects `RUN git config ...` steps that fail with "git: not found".
# curl + zstd needed for Ollama install. libpq5 for psycopg runtime.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    postgresql-client \
    curl \
    wget \
    zstd \
    bash \
    git \
    git-lfs \
    procps \
    && git lfs install \
    && curl -fsSL https://ollama.com/install.sh | sh \
    && rm -rf /var/lib/apt/lists/*

COPY --from=uvbin /uv /uvx /bin/
COPY --from=builder /opt/venv /opt/venv

# Create non-root app user (UID 1000 — MANDATORY for HF Spaces)
RUN useradd --create-home --uid 1000 --shell /bin/bash appuser && \
    mkdir -p /app/staticfiles /app/media /app/logs /home/appuser/.ollama && \
    chown -R appuser:appuser /app /home/appuser

WORKDIR /app

# Copy application source (after deps — maximizes layer cache hits)
COPY --chown=appuser:appuser . .

# Copy entrypoint and make executable (must be done as root before USER switch)
COPY --chown=appuser:appuser entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

USER appuser

# NOTE: Ollama models (llama3.2, nomic-embed-text) are pulled at RUNTIME
# by entrypoint.sh on first start, in a background process so the API
# starts immediately. HF persistent disk caches them for instant restarts.

# Port 7860 — mandatory for HF Spaces
EXPOSE 7860

# Health check
HEALTHCHECK --interval=30s --timeout=15s --start-period=120s --retries=3 \
    CMD curl -fsS "http://127.0.0.1:${PORT:-7860}/api/v1/health/" || exit 1

ENTRYPOINT ["/entrypoint.sh"]
CMD ["api"]
