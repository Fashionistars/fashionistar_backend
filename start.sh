#!/usr/bin/env bash

# Exit on error
set -o errexit

echo "Starting Gunicorn and Celery Beat..."

# Start Gunicorn web server in the background
# Use the PORT environment variable provided by Render
gunicorn backend.wsgi --bind 0.0.0.0:${PORT} --workers 2 --threads 2 &

# Start Celery Beat scheduler in the background
celery -A backend beat -l info &

# Wait for any process to exit
wait -n

# Exit with status of process that exited first
exit $?