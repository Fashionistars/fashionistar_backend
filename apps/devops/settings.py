# apps/devops/settings.py
"""
DevOps application settings.
All logging is handled centrally by backend.apps.BackendConfig.
"""
from django.conf import settings
import os

# Docker Settings
DOCKER_COMPOSE_FILE = getattr(settings, 'DOCKER_COMPOSE_FILE', 'docker-compose.yml')
DOCKER_COMPOSE_PROD_FILE = getattr(settings, 'DOCKER_COMPOSE_PROD_FILE', 'docker-compose.prod.yml')
DOCKER_COMPOSE_STAGING_FILE = getattr(settings, 'DOCKER_COMPOSE_STAGING_FILE', 'docker-compose.staging.yml')

# Health Check Settings
HEALTH_CHECK_TIMEOUT = getattr(settings, 'HEALTH_CHECK_TIMEOUT', 30)  # seconds
HEALTH_CHECK_INTERVAL = getattr(settings, 'HEALTH_CHECK_INTERVAL', 300)  # 5 minutes

# Deployment Settings
DEPLOYMENT_TIMEOUT = getattr(settings, 'DEPLOYMENT_TIMEOUT', 1800)  # 30 minutes
DEPLOYMENT_LOG_RETENTION_DAYS = getattr(settings, 'DEPLOYMENT_LOG_RETENTION_DAYS', 90)

# Backup Settings
BACKUP_DIR = getattr(settings, 'BACKUP_DIR', '/tmp/fashionistar_backups')
BACKUP_RETENTION_DAYS = getattr(settings, 'BACKUP_RETENTION_DAYS', 30)

# Monitoring Settings
HEALTH_CHECK_RETENTION_DAYS = getattr(settings, 'HEALTH_CHECK_RETENTION_DAYS', 30)
SYSTEM_MONITOR_INTERVAL = getattr(settings, 'SYSTEM_MONITOR_INTERVAL', 600)  # 10 minutes

# Security Settings
SECRET_ENCRYPTION_KEY = getattr(settings, 'SECRET_ENCRYPTION_KEY', settings.SECRET_KEY)
MAX_DEPLOYMENT_ATTEMPTS = getattr(settings, 'MAX_DEPLOYMENT_ATTEMPTS', 3)

# Rate Limiting Settings
RATE_LIMIT_HEALTH_CHECK = getattr(settings, 'RATE_LIMIT_HEALTH_CHECK', '10/m')
RATE_LIMIT_DEPLOYMENT = getattr(settings, 'RATE_LIMIT_DEPLOYMENT', '5/h')
RATE_LIMIT_DOCKER_OPS = getattr(settings, 'RATE_LIMIT_DOCKER_OPS', '20/m')

# Celery settings
CELERY_DEVOPS_QUEUE = getattr(settings, 'CELERY_DEVOPS_QUEUE', 'devops')

# Default Health Check URLs
DEFAULT_HEALTH_CHECK_URLS = {
    'development': 'http://localhost:8001/health/',
    'staging': 'https://staging.fashionistar.io/health/',
    'production': 'https://fashionistar.io/health/',
    'testing': 'http://localhost:8001/health/',
}

# Default environments configuration
DEFAULT_ENVIRONMENTS = [
    {
        'name': 'development',
        'environment_type': 'development',
        'description': 'Local development environment'
    },
    {
        'name': 'staging', 
        'environment_type': 'staging',
        'description': 'Staging environment for pre-prod testing'
    },
    {
        'name': 'production',
        'environment_type': 'production', 
        'description': 'Main production environment'
    }
]

# Default monitoring services
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