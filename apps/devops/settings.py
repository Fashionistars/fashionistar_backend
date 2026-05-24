"""
تنظیمات خاص اپلیکیشن DevOps
"""
from django.conf import settings
import os


# تنظیمات Docker
DOCKER_COMPOSE_FILE = getattr(settings, 'DOCKER_COMPOSE_FILE', 'docker-compose.yml')
DOCKER_COMPOSE_PROD_FILE = getattr(settings, 'DOCKER_COMPOSE_PROD_FILE', 'docker-compose.prod.yml')
DOCKER_COMPOSE_STAGING_FILE = getattr(settings, 'DOCKER_COMPOSE_STAGING_FILE', 'docker-compose.staging.yml')

# تنظیمات Health Check
HEALTH_CHECK_TIMEOUT = getattr(settings, 'HEALTH_CHECK_TIMEOUT', 30)  # ثانیه
HEALTH_CHECK_INTERVAL = getattr(settings, 'HEALTH_CHECK_INTERVAL', 300)  # 5 دقیقه

# تنظیمات Deployment
DEPLOYMENT_TIMEOUT = getattr(settings, 'DEPLOYMENT_TIMEOUT', 1800)  # 30 دقیقه
DEPLOYMENT_LOG_RETENTION_DAYS = getattr(settings, 'DEPLOYMENT_LOG_RETENTION_DAYS', 90)

# تنظیمات پشتیبان‌گیری
BACKUP_DIR = getattr(settings, 'BACKUP_DIR', '/tmp/helssa_backups')
BACKUP_RETENTION_DAYS = getattr(settings, 'BACKUP_RETENTION_DAYS', 30)

# تنظیمات مانیتورینگ
HEALTH_CHECK_RETENTION_DAYS = getattr(settings, 'HEALTH_CHECK_RETENTION_DAYS', 30)
SYSTEM_MONITOR_INTERVAL = getattr(settings, 'SYSTEM_MONITOR_INTERVAL', 600)  # 10 دقیقه

# تنظیمات امنیتی
SECRET_ENCRYPTION_KEY = getattr(settings, 'SECRET_ENCRYPTION_KEY', settings.SECRET_KEY)
MAX_DEPLOYMENT_ATTEMPTS = getattr(settings, 'MAX_DEPLOYMENT_ATTEMPTS', 3)

# تنظیمات Rate Limiting
RATE_LIMIT_HEALTH_CHECK = getattr(settings, 'RATE_LIMIT_HEALTH_CHECK', '10/m')
RATE_LIMIT_DEPLOYMENT = getattr(settings, 'RATE_LIMIT_DEPLOYMENT', '5/h')
RATE_LIMIT_DOCKER_OPS = getattr(settings, 'RATE_LIMIT_DOCKER_OPS', '20/m')

# تنظیمات Celery
CELERY_DEVOPS_QUEUE = getattr(settings, 'CELERY_DEVOPS_QUEUE', 'devops')

# URL های پیش‌فرض
DEFAULT_HEALTH_CHECK_URLS = {
    'development': 'http://localhost:8000/health/',
    'staging': 'https://staging.helssa.ir/health/',
    'production': 'https://helssa.ir/health/',
    'testing': 'http://localhost:8000/health/',
}

# تنظیمات environment های پیش‌فرض
DEFAULT_ENVIRONMENTS = [
    {
        'name': 'development',
        'environment_type': 'development',
        'description': 'محیط توسعه محلی'
    },
    {
        'name': 'staging', 
        'environment_type': 'staging',
        'description': 'محیط تست قبل از production'
    },
    {
        'name': 'production',
        'environment_type': 'production', 
        'description': 'محیط تولید اصلی'
    }
]

# سرویس‌های پیش‌فرض برای مانیتورینگ
DEFAULT_MONITORING_SERVICES = {
    'web': {
        'service_type': 'web',
        'check_interval': 300,
        'timeout': 30
    },
    'database': {
        'service_type': 'database',
        'check_interval': 600,
        'timeout': 15
    },
    'cache': {
        'service_type': 'cache',
        'check_interval': 300,
        'timeout': 10
    },
    'storage': {
        'service_type': 'storage',
        'check_interval': 600,
        'timeout': 20
    },
    'proxy': {
        'service_type': 'proxy',
        'check_interval': 180,
        'timeout': 10
    }
}

# تنظیمات لاگ
DEVOPS_LOGGER_CONFIG = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'devops_formatter': {
            'format': '{asctime} [{levelname}] {name}: {message}',
            'style': '{',
        },
    },
    'handlers': {
        'devops_file': {
            'level': 'INFO',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': os.path.join(getattr(settings, 'LOG_DIR', '/tmp'), 'devops.log'),
            'maxBytes': 1024*1024*10,  # 10MB
            'backupCount': 5,
            'formatter': 'devops_formatter',
        },
        'devops_console': {
            'level': 'INFO',
            'class': 'logging.StreamHandler',
            'formatter': 'devops_formatter',
        },
    },
    'loggers': {
        'devops': {
            'handlers': ['devops_file', 'devops_console'],
            'level': 'INFO',
            'propagate': False,
        },
        'devops.services': {
            'handlers': ['devops_file'],
            'level': 'DEBUG',
            'propagate': False,
        },
    },
}

# اعمال تنظیمات لاگ
import logging.config
logging.config.dictConfig(DEVOPS_LOGGER_CONFIG)