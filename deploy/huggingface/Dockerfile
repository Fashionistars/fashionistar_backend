# =============================================================================
# FASHIONISTAR — Production Dockerfile (Hugging Face Spaces + Multi-Platform)
# =============================================================================
# Primary Target:  Hugging Face Spaces (Docker SDK — linux/amd64)
# Also Works:      Northflank, Render, Railway, Oracle Cloud, local dev
#
# Hugging Face Constraints (mandatory):
#   ✓ Port must be 7860  (overridable via PORT env for other platforms)
#   ✓ Run as non-root UID 1000 (appuser)
#   ✓ No local disk writes — use Cloudinary/S3
#
# Build for HF Spaces (AMD64 — HF default):
#   docker buildx build --platform linux/amd64 -f Dockerfile.production -t fashionistar/api:latest .
#
# Build multi-arch (for Oracle Cloud ARM64 + HF AMD64):
#   docker buildx build --platform linux/arm64,linux/amd64 -f Dockerfile.production --push \
#     -t ghcr.io/fashionistars/fashionistar_backend/api:latest .
# =============================================================================

# ── Stage 1: uv binary ───────────────────────────────────────────────────────
# NOTE: Versions are hardcoded (not ARG) because HF Spaces injects secrets
# as Docker build args, which override ARG defaults and cause build failures.
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

# ── Stage 3: production runtime (minimal image) ──────────────────────────────
FROM python:3.13-slim AS runner

# Runtime environment
# PORT=7860 is mandatory for Hugging Face Spaces.
# The entrypoint.sh auto-detects the platform and overrides PORT if needed
# for other platforms (e.g. Northflank=8080, Render=10000, Oracle=10000).
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH" \
    DJANGO_SETTINGS_MODULE=backend.config.production \
    WORKING_ENVIRONMENT=production \
    PORT=7860 \
    UVICORN_WS=auto \
    GUNICORN_WORKERS=3 \
    GUNICORN_TIMEOUT=900 \
    GUNICORN_KEEPALIVE=900 \
    GUNICORN_MAX_REQUESTS=1000 \
    GUNICORN_MAX_REQUESTS_JITTER=100 \
    GUNICORN_LOG_LEVEL=info

# Runtime system dependencies only (no build tools — keeps image small)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    postgresql-client \
    curl \
    zstd \
    && curl -fsSL https://ollama.com/install.sh | sh \
    && rm -rf /var/lib/apt/lists/*

COPY --from=uvbin /uv /uvx /bin/
COPY --from=builder /opt/venv /opt/venv

# Create non-root app user:
# UID 1000 is MANDATORY for Hugging Face Spaces [HF Platform Requirement].
# Also matches best practices for all other platforms.
RUN useradd --create-home --uid 1000 --shell /bin/sh appuser && \
    mkdir -p /app/staticfiles /app/media /app/logs /home/appuser/.ollama && \
    chown -R appuser:appuser /app /home/appuser

WORKDIR /app

# Copy application source (after deps — maximizes layer cache hits)
COPY --chown=appuser:appuser . .

# Copy entrypoint and make executable (must be done as root before USER switch)
COPY --chown=appuser:appuser entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

USER appuser

# Pre-pull Ollama models during build to keep startup instant
RUN ollama serve & \
    sleep 5 && \
    ollama pull llama3.2 && \
    ollama pull nomic-embed-text && \
    pkill -f ollama

# Expose port 7860 (Hugging Face standard).
# For other platforms, Docker ignores EXPOSE — actual port is set via PORT env var.
EXPOSE 7860

# Health check — polls /api/v1/health/ endpoint
HEALTHCHECK --interval=30s --timeout=15s --start-period=90s --retries=3 \
    CMD curl -fsS "http://127.0.0.1:${PORT:-7860}/api/v1/health/" || exit 1

ENTRYPOINT ["/entrypoint.sh"]

# Default command: start the production API server.
# The entrypoint.sh auto-detects platform + port.
# For Celery: override with CMD ["celery-worker"] or CMD ["celery-beat"]
CMD ["api"]
