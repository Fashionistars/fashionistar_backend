#!/bin/sh

set -eu

log() {
  printf '%s\n' "$1"
}

run_manage() {
  uv run python manage.py "$@"
}

DB_HOST="${DB_HOST:-}"
DB_PORT="${DB_PORT:-5432}"
DB_USER="${DB_USER:-postgres}"
DB_NAME="${DB_NAME:-fashionistar}"
DEBUG_VALUE="${DEBUG:-False}"
PORT_VALUE="${PORT:-8001}"

log "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
log "FASHIONISTAR backend container bootstrap"
log "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━═════════════════════════════════════════════════════════════════════"
if [ -n "$DB_HOST" ]; then
  log "Waiting for PostgreSQL at ${DB_HOST}:${DB_PORT}..."
  ATTEMPT=0
  until pg_isready -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" >/dev/null 2>&1; do
    ATTEMPT=$((ATTEMPT + 1))
    if [ "$ATTEMPT" -ge "${DB_WAIT_TIMEOUT:-45}" ]; then
      log "Database was not reachable within ${DB_WAIT_TIMEOUT:-45} seconds."
      exit 1
    fi
    sleep 1
  done
  log "PostgreSQL is reachable."
fi

if [ "${RUN_MIGRATIONS:-1}" = "1" ]; then
  log "Running Django migrations..."
  run_manage migrate --noinput
fi

if [ "${RUN_COLLECTSTATIC:-auto}" = "1" ] || {
  [ "${RUN_COLLECTSTATIC:-auto}" = "auto" ] && [ "$DEBUG_VALUE" != "True" ] && [ "$DEBUG_VALUE" != "true" ];
}; then
  log "Collecting static files..."
  run_manage collectstatic --noinput
fi

log "Verifying Django configuration..."
run_manage check --deploy --fail-level WARNING >/dev/null 2>&1 || run_manage check >/dev/null

log "Bootstrap complete."
log "Settings: ${DJANGO_SETTINGS_MODULE:-backend.config.production}"
log "Database: ${DB_HOST:-local}:${DB_PORT}/${DB_NAME}"
log "Redis: ${REDIS_URL:-${REDIS_HOST:-unset}}"
log "Port: ${PORT_VALUE}"

exec "$@"
