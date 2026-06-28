# apps/scheduler/settings.py
"""
Settings for the scheduler app.
All Celery task queues, routes, and beat schedules have been centralized in backend/celery.py.
"""
import os

# ======================
# Scheduler App Settings
# ======================

# Cleanup settings
SCHEDULER_CLEANUP_DAYS = int(os.getenv('SCHEDULER_CLEANUP_DAYS', 30))
SCHEDULER_LOG_CLEANUP_DAYS = int(os.getenv('SCHEDULER_LOG_CLEANUP_DAYS', 7))

# Alert thresholds
SCHEDULER_ALERT_THRESHOLD_MINUTES = int(os.getenv('SCHEDULER_ALERT_THRESHOLD_MINUTES', 5))
SCHEDULER_PERFORMANCE_THRESHOLD_PERCENT = int(os.getenv('SCHEDULER_PERFORMANCE_THRESHOLD_PERCENT', 50))

# Execution defaults
SCHEDULER_DEFAULT_MAX_RETRIES = int(os.getenv('SCHEDULER_DEFAULT_MAX_RETRIES', 3))
SCHEDULER_DEFAULT_RETRY_DELAY = int(os.getenv('SCHEDULER_DEFAULT_RETRY_DELAY', 60))
SCHEDULER_DEFAULT_PRIORITY = int(os.getenv('SCHEDULER_DEFAULT_PRIORITY', 5))

# Limits
SCHEDULER_MAX_EXECUTION_HISTORY = int(os.getenv('SCHEDULER_MAX_EXECUTION_HISTORY', 1000))
SCHEDULER_MAX_LOG_PER_EXECUTION = int(os.getenv('SCHEDULER_MAX_LOG_PER_EXECUTION', 100))

# ======================
# Django Celery Beat
# ======================

# Enable django-celery-beat database scheduler
USE_DJANGO_CELERY_BEAT = os.getenv('USE_DJANGO_CELERY_BEAT', 'False').lower() == 'true'

if USE_DJANGO_CELERY_BEAT:
    CELERY_BEAT_SCHEDULER = 'django_celery_beat.schedulers:DatabaseScheduler'
    DJANGO_CELERY_BEAT_TZ_AWARE = True
    CELERY_BEAT_SCHEDULE_FILENAME = 'celerybeat-schedule'

# ======================
# Security Settings
# ======================

# API Rate Limits
SCHEDULER_API_RATE_LIMIT = os.getenv('SCHEDULER_API_RATE_LIMIT', '100/hour')

# IP whitelist for sensitive executions
SCHEDULER_ALLOWED_IPS = os.getenv('SCHEDULER_ALLOWED_IPS', '').split(',') if os.getenv('SCHEDULER_ALLOWED_IPS') else []

# ======================
# Integration Settings
# ======================

# Enable alerts/audit integrations
SCHEDULER_ENABLE_NOTIFICATIONS = os.getenv('SCHEDULER_ENABLE_NOTIFICATIONS', 'True').lower() == 'true'
SCHEDULER_ENABLE_AUDIT_LOG = os.getenv('SCHEDULER_ENABLE_AUDIT_LOG', 'True').lower() == 'true'

# Webhook settings
SCHEDULER_WEBHOOK_TIMEOUT = int(os.getenv('SCHEDULER_WEBHOOK_TIMEOUT', 30))
SCHEDULER_WEBHOOK_MAX_RETRIES = int(os.getenv('SCHEDULER_WEBHOOK_MAX_RETRIES', 3))