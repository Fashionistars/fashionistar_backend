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
  - Explicit localhost/tunnel CORS + CSRF allowlists
  - BrowsableAPIRenderer enabled
  - No HTTPS/HSTS enforcement
"""

from backend.config.base import *  # noqa: F401,F403

# =============================================================================
# CORE — Debug ON
# =============================================================================
DEBUG = True

# Development must explicitly neutralize the security flags computed in base.py
# so local HTTP and tunnel-driven QA flows behave like a true dev environment.
SECURE_HSTS_SECONDS = 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_HSTS_PRELOAD = False
SECURE_SSL_REDIRECT = False
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False

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

# ── Tunnel URLs (dynamic — read from .env, never hardcoded) ────────────────
_frontend_tunnel = env("FRONTEND_TUNNEL_URL", default=None)  # noqa: F405
_backend_tunnel  = env("BACKEND_TUNNEL_URL", default=None)   # noqa: F405

_csrf_origins = build_origin_list(  # noqa: F405
    'http://localhost:8000',
    'http://127.0.0.1:8000',
    'http://localhost:8001',       # Uvicorn ASGI
    'http://127.0.0.1:8001',      # Uvicorn ASGI
    'http://0.0.0.0:8000',
    'http://0.0.0.0:8001',
    'http://localhost:3000',       # Next.js frontend
    'http://localhost:3001',       # Next.js frontend alt port
    'http://localhost:3002',
    'http://localhost:3100',       # Isolated live-E2E frontend instance
    'http://127.0.0.1:3002',
    'http://127.0.0.1:3100',
    'http://0.0.0.0:3000',
    'http://0.0.0.0:3001',
    'http://0.0.0.0:3002',
    'http://0.0.0.0:3100',
    FRONTEND_URL,  # noqa: F405
    _frontend_tunnel,
)

CSRF_TRUSTED_ORIGINS = build_origin_list(  # noqa: F405
    *CSRF_TRUSTED_ORIGINS,
    *_csrf_origins,
)


# =============================================================================
# EMAIL — Console Backend for Testing
# =============================================================================
# Emails print to the terminal instead of sending — perfect for development.
# To see the OTP email content: run server, register, watch terminal.
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'


# =============================================================================
# CORS — Explicit localhost/tunnel origins for frontend dev
# =============================================================================
CORS_ALLOW_ALL_ORIGINS = False
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOWED_ORIGINS = build_origin_list(  # noqa: F405
    *CORS_ALLOWED_ORIGINS,
    'http://localhost:3000',
    'http://127.0.0.1:3000',
    'http://localhost:3001',
    'http://127.0.0.1:3001',
    'http://localhost:3002',
    'http://127.0.0.1:3002',
    'http://localhost:3100',
    'http://127.0.0.1:3100',
    'http://0.0.0.0:3000',
    'http://0.0.0.0:3001',
    'http://0.0.0.0:3002',
    'http://0.0.0.0:3100',
    FRONTEND_URL,  # noqa: F405
    _frontend_tunnel,
)


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


# =============================================================================
# GOOGLE OAUTH2 (development)
# =============================================================================
GOOGLE_CLIENT_ID     = env("GOOGLE_CLIENT_ID", default="")      # noqa: F405
GOOGLE_CLIENT_SECRET = env("GOOGLE_CLIENT_SECRET", default="")  # noqa: F405
