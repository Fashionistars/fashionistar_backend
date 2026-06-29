#!/usr/bin/env bash

# Exit immediately if a command exits with a non-zero status.
set -o errexit

echo "Starting Uvicorn, Celery Worker, and Celery Beat..."

# Run database migrations before starting servers
python manage.py migrate --noinput

# Start Uvicorn web server in the background.
# --workers 1 is optimal for the free tier's shared CPU.
# --timeout-keep-alive 120 matches our ASGI timeout configurations.
uvicorn backend.asgi:application --host 0.0.0.0 --port ${PORT:-8001} --workers 1 --ws auto --timeout-keep-alive 120 --log-config uvicorn_log_config.json &

# Start Celery Worker in the background.
# --concurrency=1 is best for the free tier.
# --max-tasks-per-child=100 prevents memory leaks over time (critical for stability).
# --without-gossip --without-mingle makes it more lightweight.
# Using 'solo' pool is safer for low-memory environments.
celery -A backend worker -l info --pool=solo --concurrency=1 --without-gossip --without-mingle --max-tasks-per-child=100 &

# Start Celery Beat scheduler in the background.
# --scheduler django_celery_beat... explicitly uses the database for schedules.
celery -A backend beat -l info --scheduler django_celery_beat.schedulers:DatabaseScheduler &

# Wait for any of the background processes to exit.
wait -n

# Exit with the status of the process that exited first.
exit $?