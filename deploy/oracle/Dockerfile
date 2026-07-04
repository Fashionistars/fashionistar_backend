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
    PORT=8001 \
    UVICORN_WORKERS=1 \
    UVICORN_KEEP_ALIVE=120 \
    UVICORN_WS=auto

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

EXPOSE 8001

HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -fsS "http://127.0.0.1:${PORT}/health/" || exit 1

ENTRYPOINT ["/entrypoint.sh"]

CMD ["sh", "-c", "exec uv run --no-sync uvicorn backend.asgi:application --host 0.0.0.0 --port ${PORT:-8001} --workers ${UVICORN_WORKERS:-1} --ws ${UVICORN_WS:-auto} --timeout-keep-alive ${UVICORN_KEEP_ALIVE:-120} --log-config uvicorn_log_config.json"]
