# Multi-stage build for optimized production image using Astral uv
ARG PYTHON_VERSION=3.12-slim

# ═══════════════════════════════════════════════════════════
# Stage 1: Builder - Install dependencies inside a virtual env
# ═══════════════════════════════════════════════════════════
FROM python:${PYTHON_VERSION} AS builder

# Set environment variables for compilation and uv
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

# Install system dependencies for building psycopg and cryptography
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Astral uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Copy dependency definition files
COPY pyproject.toml uv.lock ./

# Install python dependencies into a virtual environment in /opt/venv
RUN uv venv /opt/venv && \
    VIRTUAL_ENV=/opt/venv uv sync --frozen --no-dev --no-editable --no-install-project

# ═══════════════════════════════════════════════════════════
# Stage 2: Production Runtime - Minimal image
# ═══════════════════════════════════════════════════════════
FROM python:${PYTHON_VERSION}

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    DJANGO_SETTINGS_MODULE=backend.config.production

# Install only runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    postgresql-client \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Astral uv inside runtime as well so we can execute with 'uv run'
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Copy virtual environment from builder stage
COPY --from=builder /opt/venv /opt/venv

# Create non-root application user
RUN useradd -m -u 1000 appuser && \
    mkdir -p /app/staticfiles /app/media && \
    chown -R appuser:appuser /app

WORKDIR /app

# Copy application code with proper permissions
COPY --chown=appuser:appuser . .

# Create entrypoint script
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh && chown appuser:appuser /entrypoint.sh

# Switch to non-root user
USER appuser

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/health/ || exit 1

# Run entrypoint script
ENTRYPOINT ["/entrypoint.sh"]

# Default command: Start Uvicorn ASGI server directly inside the uv environment
CMD ["uv", "run", "uvicorn", "backend.asgi:application", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "4", \
     "--ws", "auto", \
     "--timeout-keep-alive", "120", \
     "--log-config", "uvicorn_log_config.json"]
