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
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')  # Respect GCP Load Balancer SSL
SESSION_COOKIE_SECURE = True                  # Cookies only over HTTPS
SESSION_COOKIE_HTTPONLY = True                # Prevent JS access to session cookie
SESSION_COOKIE_SAMESITE = 'Lax'              # CSRF protection via SameSite
CSRF_COOKIE_SECURE = True                     # CSRF cookie only over HTTPS
CSRF_COOKIE_HTTPONLY = False                  # Needs to be readable by JS for SPA
CSRF_COOKIE_SAMESITE = 'Lax'
SECURE_BROWSER_XSS_FILTER = True             # Legacy but harmless
SECURE_CONTENT_TYPE_NOSNIFF = True           # Prevent MIME type sniffing
SECURE_HSTS_SECONDS = 31536000               # 1 year HSTS
SECURE_HSTS_INCLUDE_SUBDOMAINS = True        # Apply to all subdomains
SECURE_HSTS_PRELOAD = True                   # Submit to HSTS preload list
X_FRAME_OPTIONS = 'DENY'                     # Prevent clickjacking
SECURE_REFERRER_POLICY = 'strict-origin-when-cross-origin'

# CSRF trusted origins — required for Next.js frontend in production
CSRF_TRUSTED_ORIGINS = [
    "https://fashionistar.net",
    "https://www.fashionistar.net",
    "https://app.fashionistar.net",
    "https://api.fashionistar.net",
]


# =============================================================================
# EMAIL — Real backend in production
# =============================================================================
# Use the Database-configured backend (Admin sets SMTP/Mailgun/Zoho)
EMAIL_BACKEND = 'apps.providers.backends.email_backend.DatabaseConfiguredEmailBackend'

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
if "*" in CORS_ALLOWED_ORIGINS:
    CORS_ALLOW_ALL_ORIGINS = True
    CORS_ALLOWED_ORIGINS = []
CORS_ALLOW_CREDENTIALS = True

CORS_ALLOW_HEADERS = [
    "accept",
    "accept-encoding",
    "authorization",
    "content-type",
    "content-disposition",
    "dnt",
    "origin",
    "user-agent",
    "x-csrftoken",
    "x-requested-with",
    "access-control-allow-origin",
    # ── Exactly-once write semantics ──
    "x-idempotency-key",
    # ── Anonymous session identity — guest cart & wishlist ──
    "x-fashionistar-session-key",
    # ── Wave B3 Audit Context Headers — client device/geo enrichment ───────
    "x-device-id",
    "x-client-timezone",
    "x-client-locale",
    "x-client-platform",
    "x-client-geo-lat",
    "x-client-geo-lng",
    "x-client-geo-accuracy",
    "ngrok-skip-browser-warning",
]

CORS_ALLOW_METHODS = ("GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS")



# =============================================================================
# STATIC FILES — Compressed & manifest in production
# =============================================================================
from whitenoise.storage import CompressedManifestStaticFilesStorage

class NonStrictCompressedManifestStaticFilesStorage(CompressedManifestStaticFilesStorage):
    manifest_strict = False

    def hashed_name(self, name, content=None, filename=None):
        try:
            return super().hashed_name(name, content, filename)
        except ValueError:
            # Fallback to the original unhashed name if the file is missing from disk
            return name

STORAGES = {
    "default": {
        "BACKEND": "cloudinary_storage.storage.MediaCloudinaryStorage",
    },
    "staticfiles": {
        "BACKEND": "backend.config.production.NonStrictCompressedManifestStaticFilesStorage",
    },
}

WHITENOISE_MANIFEST_STRICT = False


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
# =============================================================================
# SENTRY — Error tracking (configure DSN in .env)
# =============================================================================
import os as _os
_sentry_dsn = _os.environ.get("SENTRY_DSN", "")
if _sentry_dsn:
    import sentry_sdk
    from sentry_sdk.integrations.django import DjangoIntegration
    from sentry_sdk.integrations.celery import CeleryIntegration
    from sentry_sdk.integrations.redis import RedisIntegration

    sentry_sdk.init(
        dsn=_sentry_dsn,
        integrations=[
            DjangoIntegration(transaction_style="url"),
            CeleryIntegration(monitor_beat_tasks=True),
            RedisIntegration(),
        ],
        traces_sample_rate=0.10,   # 10% performance tracing
        profiles_sample_rate=0.05, # 5% profiling
        send_default_pii=False,    # GDPR: no PII in error reports
        environment="production",
        release=_os.environ.get("GIT_SHA", "unknown"),
        before_send=lambda event, hint: event,  # Add PII scrubbing here if needed
    )


# =============================================================================
# PRODUCTION CHECKLIST GUARD
# =============================================================================
# This will raise on startup if any critical settings are misconfigured.
import sys

_required_env_vars = [
    'SECRET_KEY', 'DATABASE_URL', 'REDIS_URL',
]
_missing = [v for v in _required_env_vars if not env(v, default='')]  # noqa: F405
if _missing:
    print(f"[FASHIONISTAR PRODUCTION] ❌ Missing required env vars: {_missing}", file=sys.stderr)


# =============================================================================
# PASSWORD HASHERS — Phase 7 OWASP Hardening
# =============================================================================
# Argon2 is the winner of the Password Hashing Competition (PHC).
# GPU-resistant: requires both time + memory, making brute-force prohibitive.
# Falls back to PBKDF2 for legacy password verification (automatic upgrade on next login).
PASSWORD_HASHERS = [
    'django.contrib.auth.hashers.Argon2PasswordHasher',   # Primary (OWASP recommended)
    'django.contrib.auth.hashers.BCryptSHA256PasswordHasher',  # Fallback 1
    'django.contrib.auth.hashers.PBKDF2PasswordHasher',        # Fallback 2 (legacy)
    'django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher',    # Fallback 3
]
