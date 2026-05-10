#!/usr/bin/env bash

# Exit on error
set -o errexit

echo "Starting Gunicorn, Celery Worker, and Celery Beat..."

# Start Gunicorn (your main web application) in the background
# Adjust workers/threads if needed, but keep them low for free tier.
# Use --bind 0.0.0.0:${PORT} for Render.
gunicorn backend.wsgi:application --bind 0.0.0.0:${PORT} --workers 1 --threads 2 --timeout 60 --log-level info &

# Start Celery Worker in the background
# Adjust concurrency based on free tier limits. Low concurrency is expected.
# Using 'solo' worker pool to avoid multiprocessing issues when bundled with Gunicorn,
# or for very resource-constrained environments.
# If you have gevent installed and many IO-bound tasks, you might try -P gevent --concurrency=2
celery -A backend worker -l info --concurrency=1 --without-gossip --without-mingle --max-tasks-per-child 100 &

# Start Celery Beat in the background
# Crucial: Beat needs to store its schedule persistently.
# For django-celery-beat, it uses the database.
celery -A backend beat -l info --scheduler django_celery_beat.schedulers:DatabaseScheduler &

# Wait for all background processes to finish (this keeps the Render service alive)
wait -n

# Exit with status of last exited background process
exit $?