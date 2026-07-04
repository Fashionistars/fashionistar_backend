#!/usr/bin/env bash
# =============================================================================
# FASHIONISTAR — Universal Dynamic Entrypoint
# =============================================================================
# Automatically detects the hosting platform and configures the server:
#
#   Platform Detection:
#   ┌─────────────────────────────────────────────────────────────────────┐
#   │  SPACE_ID          env set → Hugging Face Spaces  → PORT=7860      │
#   │  NORTHFLANK_*      env set → Northflank            → Celery mode    │
#   │  IS_RENDER_ENV     env set → Render.com            → PORT env var   │
#   │  RAILWAY_*         env set → Railway.app           → PORT env var   │
#   │  FLY_APP_NAME      env set → Fly.io                → PORT env var   │
#   │  ORACLE_CLOUD_*    env set → Oracle Cloud VM       → PORT=10000     │
#   │  DEFAULT                  → Auto from $PORT or 8000                │
#   └─────────────────────────────────────────────────────────────────────┘
#
# Usage (in Dockerfile CMD / platform runtime):
#   entrypoint.sh                    → API server (auto-detects port)
#   entrypoint.sh celery-worker      → Celery worker mode
#   entrypoint.sh celery-beat        → Celery beat scheduler mode
#   entrypoint.sh migrate            → Run migrations only and exit
#   entrypoint.sh shell              → Django shell
# =============================================================================

set -o errexit
set -o pipefail
set -o nounset

# ── Color helpers ─────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

log_info()    { echo -e "${GREEN}[✓] $*${NC}"; }
log_warn()    { echo -e "${YELLOW}[!] $*${NC}"; }
log_error()   { echo -e "${RED}[✗] $*${NC}"; }
log_section() { echo -e "\n${BOLD}${CYAN}══════════════════════════════════════${NC}"; echo -e "${BOLD}${CYAN}  $*${NC}"; echo -e "${BOLD}${CYAN}══════════════════════════════════════${NC}"; }

# ── Platform Detection ────────────────────────────────────────────────────────
detect_platform() {
    if [ -n "${SPACE_ID:-}" ] || [ -n "${SPACE_AUTHOR_NAME:-}" ]; then
        echo "huggingface"
    elif env | grep -q '^NORTHFLANK_'; then
        echo "northflank"
    elif [ -n "${RENDER:-}" ] || [ -n "${IS_RENDER_ENV:-}" ]; then
        echo "render"
    elif [ "${PORT:-}" = "10000" ] || [ "${ORACLE_CLOUD:-}" = "true" ] || [ -n "${ORACLE_CLOUD_INSTANCE_ID:-}" ]; then
        echo "oracle"
    elif [ -n "${RAILWAY_ENVIRONMENT:-}" ] || [ -n "${RAILWAY_PROJECT_ID:-}" ]; then
        echo "railway"
    elif [ -n "${FLY_APP_NAME:-}" ]; then
        echo "fly"
    else
        echo "generic"
    fi
}

PLATFORM=$(detect_platform)

# ── Port Configuration (per platform) ────────────────────────────────────────
configure_port() {
    case "$PLATFORM" in
        huggingface)
            # Hugging Face REQUIRES port 7860 — non-negotiable
            export PORT=7860
            log_info "Platform: Hugging Face Spaces | Port: 7860"
            ;;
        northflank)
            # Northflank injects PORT automatically (usually 8080 for web services)
            export PORT="${PORT:-8080}"
            log_info "Platform: Northflank | Port: ${PORT}"
            ;;
        render)
            # Render injects PORT automatically (default 10000)
            export PORT="${PORT:-10000}"
            log_info "Platform: Render.com | Port: ${PORT}"
            ;;
        railway)
            # Railway injects PORT automatically
            export PORT="${PORT:-8000}"
            log_info "Platform: Railway.app | Port: ${PORT}"
            ;;
        fly)
            # Fly.io uses 8080 internally
            export PORT="${PORT:-8080}"
            log_info "Platform: Fly.io | Port: ${PORT}"
            ;;
        oracle)
            # Oracle Cloud — use fixed 10000 (matches nginx upstream)
            export PORT="${PORT:-10000}"
            log_info "Platform: Oracle Cloud | Port: ${PORT}"
            ;;
        *)
            # Generic / local dev
            export PORT="${PORT:-8000}"
            log_info "Platform: Generic/Local | Port: ${PORT}"
            ;;
    esac

    # Always ensure gunicorn.conf.py picks up the right port
    export GUNICORN_BIND="0.0.0.0:${PORT}"
}

# ── Worker Count (per platform resources) ─────────────────────────────────────
configure_workers() {
    local cpu_count
    cpu_count=$(nproc 2>/dev/null || echo "2")

    case "$PLATFORM" in
        huggingface)
            # HF free tier: 2 vCPUs → 3 workers (I/O bound formula: 2*CPU+1=5, but use 3 for safety)
            export GUNICORN_WORKERS="${GUNICORN_WORKERS:-3}"
            ;;
        northflank)
            # Northflank free: limited CPU → 2 workers
            export GUNICORN_WORKERS="${GUNICORN_WORKERS:-2}"
            ;;
        render)
            # Render free: 512MB → 1-2 workers
            export GUNICORN_WORKERS="${GUNICORN_WORKERS:-2}"
            ;;
        *)
            # Auto: (2 × CPU) + 1, capped at 9
            local auto_workers=$(( (cpu_count * 2) + 1 ))
            if [ "$auto_workers" -gt 9 ]; then auto_workers=9; fi
            export GUNICORN_WORKERS="${GUNICORN_WORKERS:-$auto_workers}"
            ;;
    esac

    log_info "Gunicorn workers: ${GUNICORN_WORKERS} (CPUs detected: ${cpu_count})"
}

# ── Pre-flight Database Migrations ────────────────────────────────────────────
run_migrations() {
    log_section "Running Database Migrations"
    python manage.py migrate --noinput
    log_info "Migrations complete"
}

# ── Static Files Collection ───────────────────────────────────────────────────
run_collectstatic() {
    log_section "Collecting Static Files"
    python manage.py collectstatic --noinput --clear 2>/dev/null || \
    python manage.py collectstatic --noinput
    log_info "Static files collected"
}

# ── Main Entrypoint Logic ─────────────────────────────────────────────────────
log_section "FASHIONISTAR Universal Entrypoint"
log_info "Platform detected: ${PLATFORM}"
log_info "Django settings: ${DJANGO_SETTINGS_MODULE:-backend.config.production}"

configure_port
configure_workers

# Handle explicit mode commands
COMMAND="${1:-api}"

# On Northflank, if command is 'api', default to 'celery-worker'
if [ "$PLATFORM" = "northflank" ] && [ "$COMMAND" = "api" ]; then
    log_info "Northflank environment detected. Overriding default command 'api' to 'celery-worker'."
    COMMAND="celery-worker"
fi

case "$COMMAND" in

    # ── Celery Worker Mode ───────────────────────────────────────────────────
    celery-worker|worker)
        log_section "Starting Celery Worker (${PLATFORM})"
        export CELERY_CONCURRENCY="${CELERY_CONCURRENCY:-4}"
        export CELERY_QUEUES="${CELERY_QUEUES:-default,ai_tasks,measurements,analytics,notifications,webhooks}"
        exec celery -A backend worker \
            --loglevel="${CELERY_LOG_LEVEL:-info}" \
            --concurrency="${CELERY_CONCURRENCY}" \
            -Q "${CELERY_QUEUES}" \
            --max-tasks-per-child="${CELERY_MAX_TASKS_PER_CHILD:-100}" \
            --without-gossip \
            --without-mingle \
            --events
        ;;

    # ── Celery Beat Mode ─────────────────────────────────────────────────────
    celery-beat|beat)
        log_section "Starting Celery Beat Scheduler (${PLATFORM})"
        exec celery -A backend beat \
            --loglevel="${CELERY_LOG_LEVEL:-info}" \
            --scheduler django_celery_beat.schedulers:DatabaseScheduler \
            --max-interval=10
        ;;

    # ── Celery Worker + Beat Combined (for small free tiers) ─────────────────
    celery-all)
        log_section "Starting Celery Worker + Beat (${PLATFORM})"
        exec celery -A backend worker \
            --beat \
            --loglevel="${CELERY_LOG_LEVEL:-info}" \
            --concurrency=2 \
            -Q "default,ai_tasks,measurements,analytics,notifications,webhooks" \
            --scheduler django_celery_beat.schedulers:DatabaseScheduler \
            --max-tasks-per-child=100 \
            --without-gossip \
            --without-mingle \
            --events
        ;;

    # ── Database Migration Only ───────────────────────────────────────────────
    migrate)
        run_migrations
        log_info "Migration-only run complete. Exiting."
        exit 0
        ;;

    # ── Django Management Command passthrough ─────────────────────────────────
    manage)
        shift
        exec python manage.py "$@"
        ;;

    # ── Django Shell ──────────────────────────────────────────────────────────
    shell)
        exec python manage.py shell
        ;;

    # ── Dev Server (local development only) ───────────────────────────────────
    dev|start_dev)
        log_warn "Development mode — NOT for production use!"
        export PORT="${PORT:-8000}"
        python manage.py migrate --noinput
        python manage.py collectstatic --noinput
        exec python manage.py runserver "0.0.0.0:${PORT}"
        ;;

    # ── API Server (default — production Gunicorn + UvicornWorker) ───────────
    api|*)
        log_section "Starting FASHIONISTAR API Server (${PLATFORM})"
        log_info "Bind address: 0.0.0.0:${PORT}"
        log_info "Workers: ${GUNICORN_WORKERS}"

        # Run migrations before starting (idempotent — safe to run each deploy)
        run_migrations

        # Collect static files (fast — only copies changed files)
        run_collectstatic

        log_section "🚀 FASHIONISTAR API is Starting!"
        log_info "URL: http://0.0.0.0:${PORT}/api/v1/health/"

        exec gunicorn \
            --workers "${GUNICORN_WORKERS}" \
            --worker-class uvicorn.workers.UvicornWorker \
            --bind "0.0.0.0:${PORT}" \
            --timeout "${GUNICORN_TIMEOUT:-900}" \
            --keep-alive "${GUNICORN_KEEPALIVE:-900}" \
            --max-requests "${GUNICORN_MAX_REQUESTS:-1000}" \
            --max-requests-jitter "${GUNICORN_MAX_REQUESTS_JITTER:-100}" \
            --preload \
            --access-logfile - \
            --error-logfile - \
            --log-level "${GUNICORN_LOG_LEVEL:-info}" \
            backend.asgi:application
        ;;
esac
