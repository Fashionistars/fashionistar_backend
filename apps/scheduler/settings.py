"""
تنظیمات اپ scheduler
"""
import os
from django.conf import settings

# ======================
# Celery Configuration
# ======================

# Broker settings
CELERY_BROKER_URL = os.getenv('CELERY_BROKER_URL', 'redis://localhost:6379/0')
CELERY_RESULT_BACKEND = os.getenv('CELERY_RESULT_BACKEND', 'redis://localhost:6379/0')

# Task settings
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TIMEZONE = 'Asia/Tehran'
CELERY_ENABLE_UTC = True

# Task execution settings
CELERY_TASK_SOFT_TIME_LIMIT = 300  # 5 minutes
CELERY_TASK_TIME_LIMIT = 600  # 10 minutes
CELERY_TASK_ACKS_LATE = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1

# Task routing
CELERY_TASK_ROUTES = {
    'scheduler.execute_task': {'queue': 'scheduler'},
    'scheduler.run_scheduled_task': {'queue': 'scheduler'},
    'scheduler.cleanup_old_executions': {'queue': 'maintenance'},
    'scheduler.check_missing_executions': {'queue': 'monitoring'},
    'scheduler.monitor_task_performance': {'queue': 'monitoring'},
    'scheduler.send_task_alerts': {'queue': 'notifications'},
}

# Queue configuration
CELERY_TASK_DEFAULT_QUEUE = 'default'
CELERY_TASK_DEFAULT_EXCHANGE = 'default'
CELERY_TASK_DEFAULT_ROUTING_KEY = 'default'

from kombu import Queue, Exchange

CELERY_QUEUES = (
    Queue('default', Exchange('default'), routing_key='default'),
    Queue('scheduler', Exchange('scheduler'), routing_key='scheduler'),
    Queue('maintenance', Exchange('maintenance'), routing_key='maintenance'),
    Queue('monitoring', Exchange('monitoring'), routing_key='monitoring'),
    Queue('notifications', Exchange('notifications'), routing_key='notifications'),
)

# Beat schedule (for periodic tasks)
from celery.schedules import crontab

CELERY_BEAT_SCHEDULE = {
    # پاکسازی سوابق قدیمی - هر روز ساعت 2 صبح
    'cleanup-old-executions': {
        'task': 'scheduler.cleanup_old_executions',
        'schedule': crontab(hour=2, minute=0),
        'options': {
            'queue': 'maintenance'
        }
    },
    
    # بررسی وظایف اجرا نشده - هر 5 دقیقه
    'check-missing-executions': {
        'task': 'scheduler.check_missing_executions',
        'schedule': crontab(minute='*/5'),
        'options': {
            'queue': 'monitoring'
        }
    },
    
    # پایش عملکرد - هر ساعت
    'monitor-task-performance': {
        'task': 'scheduler.monitor_task_performance',
        'schedule': crontab(minute=0),
        'options': {
            'queue': 'monitoring'
        }
    },
    
    # ارسال هشدارها - هر 10 دقیقه
    'send-task-alerts': {
        'task': 'scheduler.send_task_alerts',
        'schedule': crontab(minute='*/10'),
        'options': {
            'queue': 'notifications'
        }
    },
}

# ======================
# Scheduler App Settings
# ======================

# تنظیمات پاکسازی
SCHEDULER_CLEANUP_DAYS = int(os.getenv('SCHEDULER_CLEANUP_DAYS', 30))
SCHEDULER_LOG_CLEANUP_DAYS = int(os.getenv('SCHEDULER_LOG_CLEANUP_DAYS', 7))

# تنظیمات هشدار
SCHEDULER_ALERT_THRESHOLD_MINUTES = int(os.getenv('SCHEDULER_ALERT_THRESHOLD_MINUTES', 5))
SCHEDULER_PERFORMANCE_THRESHOLD_PERCENT = int(os.getenv('SCHEDULER_PERFORMANCE_THRESHOLD_PERCENT', 50))

# تنظیمات اجرا
SCHEDULER_DEFAULT_MAX_RETRIES = int(os.getenv('SCHEDULER_DEFAULT_MAX_RETRIES', 3))
SCHEDULER_DEFAULT_RETRY_DELAY = int(os.getenv('SCHEDULER_DEFAULT_RETRY_DELAY', 60))
SCHEDULER_DEFAULT_PRIORITY = int(os.getenv('SCHEDULER_DEFAULT_PRIORITY', 5))

# محدودیت‌ها
SCHEDULER_MAX_EXECUTION_HISTORY = int(os.getenv('SCHEDULER_MAX_EXECUTION_HISTORY', 1000))
SCHEDULER_MAX_LOG_PER_EXECUTION = int(os.getenv('SCHEDULER_MAX_LOG_PER_EXECUTION', 100))

# ======================
# Django Celery Beat
# ======================

# اگر از django-celery-beat استفاده می‌کنید
USE_DJANGO_CELERY_BEAT = os.getenv('USE_DJANGO_CELERY_BEAT', 'False').lower() == 'true'

if USE_DJANGO_CELERY_BEAT:
    CELERY_BEAT_SCHEDULER = 'django_celery_beat.schedulers:DatabaseScheduler'
    
    # تنظیمات django-celery-beat
    DJANGO_CELERY_BEAT_TZ_AWARE = True
    CELERY_BEAT_SCHEDULE_FILENAME = 'celerybeat-schedule'

# ======================
# Logging Configuration
# ======================

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '[{levelname}] {asctime} {module} {process:d} {thread:d} {message}',
            'style': '{',
        },
        'simple': {
            'format': '[{levelname}] {asctime} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'simple',
        },
        'file': {
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': 'logs/scheduler.log',
            'maxBytes': 1024 * 1024 * 10,  # 10MB
            'backupCount': 5,
            'formatter': 'verbose',
        },
    },
    'loggers': {
        'scheduler': {
            'handlers': ['console', 'file'],
            'level': os.getenv('SCHEDULER_LOG_LEVEL', 'INFO'),
            'propagate': False,
        },
        'celery': {
            'handlers': ['console', 'file'],
            'level': os.getenv('CELERY_LOG_LEVEL', 'INFO'),
            'propagate': False,
        },
    },
}

# ======================
# Security Settings
# ======================

# محدودیت rate برای API
SCHEDULER_API_RATE_LIMIT = os.getenv('SCHEDULER_API_RATE_LIMIT', '100/hour')

# IP های مجاز برای اجرای وظایف حساس
SCHEDULER_ALLOWED_IPS = os.getenv('SCHEDULER_ALLOWED_IPS', '').split(',') if os.getenv('SCHEDULER_ALLOWED_IPS') else []

# ======================
# Integration Settings
# ======================

# ادغام با سایر اپ‌ها
SCHEDULER_ENABLE_NOTIFICATIONS = os.getenv('SCHEDULER_ENABLE_NOTIFICATIONS', 'True').lower() == 'true'
SCHEDULER_ENABLE_AUDIT_LOG = os.getenv('SCHEDULER_ENABLE_AUDIT_LOG', 'True').lower() == 'true'

# Webhook settings
SCHEDULER_WEBHOOK_TIMEOUT = int(os.getenv('SCHEDULER_WEBHOOK_TIMEOUT', 30))
SCHEDULER_WEBHOOK_MAX_RETRIES = int(os.getenv('SCHEDULER_WEBHOOK_MAX_RETRIES', 3))