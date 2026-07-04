# =============================================================================
# FASHIONISTAR — Hugging Face Spaces Dockerfile
# =============================================================================
# This is a SYMLINK/COPY of the root Dockerfile.production
# Hugging Face detects "Dockerfile" at the root of the pushed repository.
#
# For Hugging Face deployment, the GitHub Actions workflow (deploy-hf.yml)
# pushes the entire repository to huggingface.co/spaces/zichdan1999/fashionistar-api
# HF uses the root Dockerfile.production (renamed to Dockerfile when pushed).
#
# Key HF Constraints:
#   ✓ Port: 7860 (mandatory — cannot be changed)
#   ✓ User: UID 1000 (non-root mandatory)
#   ✓ SDK: Docker
#   ✓ Hardware: CPU basic • 2 vCPU • 16 GB RAM (free tier)
# =============================================================================

ARG PYTHON_VERSION=3.13-slim
ARG UV_IMAGE_TAG=0.8.22

FROM ghcr.io/astral-sh/uv:${UV_IMAGE_TAG} AS uvbin

FROM python:${PYTHON_VERSION} AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY --from=uvbin /uv /uvx /bin/

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-editable --no-install-project

FROM python:${PYTHON_VERSION} AS runner

# PORT=7860 is MANDATORY for Hugging Face Spaces
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH" \
    DJANGO_SETTINGS_MODULE=backend.config.production \
    WORKING_ENVIRONMENT=production \
    PORT=7860 \
    GUNICORN_WORKERS=3

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    postgresql-client \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=uvbin /uv /uvx /bin/
COPY --from=builder /opt/venv /opt/venv

# UID 1000 is MANDATORY for Hugging Face Spaces
RUN useradd --create-home --uid 1000 --shell /bin/sh appuser && \
    mkdir -p /app/staticfiles /app/media /app/logs && \
    chown -R appuser:appuser /app

WORKDIR /app
COPY --chown=appuser:appuser . .
COPY --chown=appuser:appuser entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

USER appuser

# Hugging Face REQUIRES port 7860
EXPOSE 7860

HEALTHCHECK --interval=30s --timeout=15s --start-period=90s --retries=3 \
    CMD curl -fsS "http://127.0.0.1:7860/api/v1/health/" || exit 1

ENTRYPOINT ["/entrypoint.sh"]
CMD ["api"]
