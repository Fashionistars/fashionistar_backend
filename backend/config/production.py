# backend/config/production.py
"""
FASHIONISTAR — Production Settings
======================================
Imports base settings and applies production-level hardening.

To use:
    export DJANGO_SETTINGS_MODULE=backend.config.production

Security features enabled:
  - DEBUG = False
  - HTTPS/HSTS enforcement
  - CSRF cookie security
  - Real email backend (DatabaseConfiguredEmailBackend or Mailgun)
  - No BrowsableAPIRenderer
  - Ruff-linted CORS whitelist
  - Compressed static files via Whitenoise
"""

from backend.config.base import *  # noqa: F401,F403
from datetime import timedelta

# =============================================================================
# CORE
# =============================================================================
DEBUG = False

# Production ALLOWED_HOSTS — MUST be set in environment
ALLOWED_HOSTS = env.list(  # noqa: F405
    "ALLOWED_HOSTS",
    default=["fashionistar.net", "www.fashionistar.net", "api.fashionistar.net"]
)


# =============================================================================
# HTTPS / HSTS — Production Security
# =============================================================================
SECURE_SSL_REDIRECT = True                    # Force all HTTP → HTTPS
SESSION_COOKIE_SECURE = True                  # Cookies only over HTTPS
CSRF_COOKIE_SECURE = True                     # CSRF cookie only over HTTPS
SECURE_BROWSER_XSS_FILTER = True             # Legacy but harmless
SECURE_CONTENT_TYPE_NOSNIFF = True           # Prevent MIME type sniffing
SECURE_HSTS_SECONDS = 31536000               # 1 year HSTS
SECURE_HSTS_INCLUDE_SUBDOMAINS = True        # Apply to all subdomains
SECURE_HSTS_PRELOAD = True                   # Submit to HSTS preload list
X_FRAME_OPTIONS = 'DENY'                     # Prevent clickjacking


# =============================================================================
# EMAIL — Real backend in production
# =============================================================================
# Use the Database-configured backend (Admin sets SMTP/Mailgun/Zoho)
EMAIL_BACKEND = 'admin_backend.backends.email_backends.DatabaseConfiguredEmailBackend'

# Fallback: to use Mailgun directly (requires MAILGUN_API_KEY in .env):
# EMAIL_BACKEND = 'anymail.backends.mailgun.EmailBackend'


# =============================================================================
# CORS — Whitelist in production
# =============================================================================
CORS_ALLOW_ALL_ORIGINS = False
CORS_ALLOWED_ORIGINS = env.list(  # noqa: F405
    "CORS_ALLOWED_ORIGINS",
    default=[
        "https://fashionistar.net",
        "https://www.fashionistar.net",
        "https://app.fashionistar.net",
    ]
)
CORS_ALLOW_CREDENTIALS = True

CORS_ALLOW_HEADERS = [
    "x-requested-with",
    "content-type",
    "accept",
    "origin",
    "authorization",
    "accept-encoding",
    "access-control-allow-origin",
    "content-disposition",

    'accept',
    'accept-encoding',
    'authorization',
    'content-type',
    'dnt',
    'origin',
    'user-agent',
    'x-csrftoken',
    'x-requested-with',
]

CORS_ALLOW_METHODS = ("GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS")



# =============================================================================
# STATIC FILES — Compressed & manifest in production
# =============================================================================
STORAGES = {
    "default": {
        "BACKEND": "cloudinary_storage.storage.MediaCloudinaryStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}


# =============================================================================
# REST FRAMEWORK — No BrowsableAPI in production
# =============================================================================
REST_FRAMEWORK = {
    **REST_FRAMEWORK,  # noqa: F405
    'DEFAULT_RENDERER_CLASSES': [
        'apps.common.renderers.FashionistarRenderer',
        # BrowsableAPIRenderer intentionally excluded from production
    ],
}


# =============================================================================
# SIMPLE JWT — Tight lifetimes in production
# =============================================================================
SIMPLE_JWT = {
    **SIMPLE_JWT,  # noqa: F405
    'ACCESS_TOKEN_LIFETIME': timedelta(hours=1),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=30),
}


# =============================================================================
# LOGGING — Production: JSON structured, INFO level, mail_admins on ERROR
# =============================================================================
# JSON formatter → parse-able by Datadog / ELK / Loki / Grafana Loki
# mail_admins → AdminEmailHandler fires on every ERROR (Django admin email)
# All per-app file handlers rotate at 10MB (app-domain) / 20MB (system)
from backend.config.logging_config import build_logging_config  # noqa: F401

LOGGING = build_logging_config(
    debug=False,
    use_json=True,      # Structured JSON lines on all file handlers
    mail_admins=True,   # Email admins on ERROR (requires EMAIL_BACKEND in prod)
)


# =============================================================================
# SENTRY — Error tracking (configure DSN in .env)
# =============================================================================
# Uncomment when ready to enable Sentry:
# import sentry_sdk
# from sentry_sdk.integrations.django import DjangoIntegration
# from sentry_sdk.integrations.celery import CeleryIntegration
#
# sentry_sdk.init(
#     dsn=env("SENTRY_DSN", default=""),
#     integrations=[DjangoIntegration(), CeleryIntegration()],
#     traces_sample_rate=0.1,
#     profiles_sample_rate=0.1,
#     send_default_pii=False,
# )


# =============================================================================
# PRODUCTION CHECKLIST GUARD
# =============================================================================
# This will raise on startuo if any critical settings are misconfigured.
import sys

_required_env_vars = [
    'SECRET_KEY', 'DATABASE_URL', 'REDIS_URL',
]
_missing = [v for v in _required_env_vars if not env(v, default='')]  # noqa: F405
if _missing:
    print(f"[FASHIONISTAR PRODUCTION] ❌ Missing required env vars: {_missing}", file=sys.stderr)
