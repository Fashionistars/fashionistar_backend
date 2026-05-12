#!/usr/bin/env bash

# Exit immediately if a command exits with a non-zero status.
set -o errexit

echo "Starting Gunicorn, Celery Worker, and Celery Beat..."

# Start Gunicorn web server in the background.
# --workers 1 is optimal for the free tier's shared CPU.
# --timeout 60 gives long requests more time to complete.
gunicorn backend.wsgi:application --bind 0.0.0.0:${PORT} --workers 1 --threads 2 --timeout 60 --log-level info &

# Start Celery Worker in the background.
# --concurrency=1 is best for the free tier.
# --max-tasks-per-child=100 prevents memory leaks over time (critical for stability).
# --without-gossip --without-mingle makes it more lightweight.
celery -A backend worker -l info --concurrency=1 --without-gossip --without-mingle --max-tasks-per-child=100 &

# Start Celery Beat scheduler in the background.
# --scheduler django_celery_beat... explicitly uses the database for schedules.
celery -A backend beat -l info --scheduler django_celery_beat.schedulers:DatabaseScheduler &

# Wait for any of the background processes to exit.
wait -n

# Exit with the status of the process that exited first.
exit $?