ARG PYTHON_VERSION=3.14-slim
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

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH" \
    DJANGO_SETTINGS_MODULE=backend.config.production \
    PORT=8001

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    postgresql-client \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=uvbin /uv /uvx /bin/
COPY --from=builder /opt/venv /opt/venv

RUN useradd --create-home --uid 1000 --shell /bin/sh appuser && \
    mkdir -p /app/staticfiles /app/media && \
    chown -R appuser:appuser /app

WORKDIR /app

COPY --chown=appuser:appuser . .

COPY --chown=appuser:appuser entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

USER appuser

ENTRYPOINT ["/entrypoint.sh"]

# Start simple python HTTP server in background to keep Cloud Run happy, and run Celery worker
CMD ["sh", "-c", "python3 -m http.server ${PORT:-8001} & exec uv run --no-sync celery -A backend worker --loglevel=info --pool=solo --events"]
