# backend/config/development.py
"""
FASHIONISTAR — Development Settings
=====================================
Imports all base settings and applies development-specific overrides.

To use:
    export DJANGO_SETTINGS_MODULE=backend.config.development
    # OR in .env:
    DJANGO_SETTINGS_MODULE=backend.config.development

Key differences from production:
  - DEBUG = True (shows error pages with tracebacks)
  - EMAIL_BACKEND = console (see emails in terminal — perfect for testing)
  - CORS_ALLOW_ALL_ORIGINS = True (open for local frontend)
  - BrowsableAPIRenderer enabled
  - No HTTPS/HSTS enforcement
"""

from backend.config.base import *  # noqa: F401,F403

# =============================================================================
# CORE — Debug ON
# =============================================================================
DEBUG = True

# Admin URL (use default for local)
DJANGO_SECRET_ADMIN_URL = env("DJANGO_SECRET_ADMIN_URL", default="admin/")  # noqa: F405


# =============================================================================
# HOSTS — Accept ALL hostnames in dev (WSGI :8000 + Uvicorn ASGI :8001)
# =============================================================================
# In development, Django may be accessed via localhost, 127.0.0.1, your machine
# hostname (e.g. FASHIONISTAR), or 0.0.0.0. Using ['*'] avoids DisallowedHost
# errors on any of these — safe ONLY in development.
# ⚠️  NEVER set ALLOWED_HOSTS = ['*'] in production.py
ALLOWED_HOSTS = ['*']

# Allow all common local origins for CSRF in dev
CSRF_TRUSTED_ORIGINS = [
    'http://localhost:8000',
    'http://127.0.0.1:8000',
    'http://localhost:8001',       # Uvicorn ASGI
    'http://127.0.0.1:8001',      # Uvicorn ASGI
    'http://0.0.0.0:8000',
    'http://0.0.0.0:8001',
    'http://localhost:3000',       # React frontend
    'http://localhost:3001',       # Next.js frontend
    'http://localhost:3002',
]


# =============================================================================
# EMAIL — Console Backend for Testing
# =============================================================================
# Emails print to the terminal instead of sending — perfect for development.
# To see the OTP email content: run server, register, watch terminal.
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'


# =============================================================================
# CORS — Open for local frontend dev
# =============================================================================
CORS_ALLOW_ALL_ORIGINS = True
CORS_ALLOW_CREDENTIALS = True


# =============================================================================
# STATIC FILES — Use simple storage in dev (no compression needed)
# =============================================================================
STORAGES = {
    "default": {
        "BACKEND": "cloudinary_storage.storage.MediaCloudinaryStorage",
    },
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
    },
}


# =============================================================================
# REST FRAMEWORK — Browsable API enabled in dev
# =============================================================================
REST_FRAMEWORK = {
    **REST_FRAMEWORK,  # noqa: F405  — inherits all base config
    'DEFAULT_RENDERER_CLASSES': [
        'apps.common.renderers.FashionistarRenderer',
        'rest_framework.renderers.BrowsableAPIRenderer',  # Dev only
    ],
}


# =============================================================================
# LOGGING — Development: DEBUG level, verbose console, no mail_admins
# =============================================================================
# Override base.py's LOGGING with debug=True explicitly.
# All per-app log files are written at DEBUG level.
# Console output is also at DEBUG so you see every SQL query, OTP email, etc.
from backend.config.logging_config import build_logging_config  # noqa: F401

LOGGING = build_logging_config(
    debug=True,
    use_json=False,     # Human-readable verbose format in dev
    mail_admins=False,  # No email on errors in dev
)


# =============================================================================
# DJANGO DEBUG TOOLBAR (optional — install django-debug-toolbar if needed)
# =============================================================================
# Uncomment below to enable:
# INSTALLED_APPS += ['debug_toolbar']
# MIDDLEWARE.insert(1, 'debug_toolbar.middleware.DebugToolbarMiddleware')
# INTERNAL_IPS = ['127.0.0.1', '::1']


# =============================================================================
# SIMPLE JWT — Longer tokens for dev convenience
# =============================================================================
from datetime import timedelta
SIMPLE_JWT = {
    **SIMPLE_JWT,  # noqa: F405
    'ACCESS_TOKEN_LIFETIME': timedelta(days=7),   # Long in dev for convenience
    'REFRESH_TOKEN_LIFETIME': timedelta(days=90),
}
