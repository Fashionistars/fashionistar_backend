#!/usr/bin/env bash

# Exit immediately if a command exits with a non-zero status.
set -o errexit

echo "Starting Uvicorn, Celery Worker, and Celery Beat using UV..."

# Run database migrations before starting servers
uv run python manage.py migrate --noinput

# Start Uvicorn web server in the background.
uv run uvicorn backend.asgi:application --host 0.0.0.0 --port ${PORT:-8001} --workers 1 --ws auto --timeout-keep-alive 120 --log-config uvicorn_log_config.json &

# Start Celery Worker in the background.
uv run celery -A backend worker -l info --pool=solo --concurrency=1 --without-gossip --without-mingle --max-tasks-per-child=100 &

# Start Celery Beat scheduler in the background.
uv run celery -A backend beat -l info --scheduler django_celery_beat.schedulers:DatabaseScheduler &

# Wait for any of the background processes to exit.
wait -n

# Exit with the status of the process that exited first.
exit $?