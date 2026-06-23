# backend/config/test.py
"""
Fashionistar — Test Settings
============================
Inherits from development.py, then applies test-specific overrides:
  - SQLite in-memory database (fast, isolated)
  - CELERY_TASK_ALWAYS_EAGER=True (run tasks inline, no broker required)
  - Disable migration framework for slow/unrelated apps
  - Console email backend (no SMTP)
  - No throttling in tests
  - Predictable SECRET_KEY
"""
from .development import *   # noqa: F401, F403 — inherit dev settings

# ─── Database — PostgreSQL if DATABASE_URL environment variable exists, otherwise SQLite ────────────────
import os
import dj_database_url
if os.environ.get("DATABASE_URL"):
    DATABASES = {
        'default': dj_database_url.config(
            default=os.environ.get("DATABASE_URL"),
            conn_max_age=600,
        )
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': 'test_db.sqlite3',
            'OPTIONS': {
                'timeout': 60,
            }
        }
    }

# ─── Celery — run tasks synchronously inside the Django test process ────────
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True   # Propagate exceptions from tasks

# ─── Email — console backend so no SMTP needed ──────────────────────────────
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

# ─── Passwords — use a faster hasher to speed up test user creation ─────────
PASSWORD_HASHERS = [
    'django.contrib.auth.hashers.MD5PasswordHasher',
]

# ─── Security ───────────────────────────────────────────────────────────────
SECRET_KEY = 'test-secret-key-not-for-production-use-only'

# ─── Throttling — disable all throttles in tests ────────────────────────────
REST_FRAMEWORK = {
    **REST_FRAMEWORK,                 # type: ignore[name-defined]
    'DEFAULT_THROTTLE_CLASSES': [],
    'DEFAULT_THROTTLE_RATES': {},
}

# ─── Cache — DummyCache so throttle counts never persist between requests ────
# BurstRateThrottle is applied directly on RegisterView (not via global setting),
# so it reads from cache. DummyCache returns None for all gets (miss), so the
# throttle count never accumulates — no 429 responses in tests.
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.dummy.DummyCache',
    }
}

# ─── Disable migrations for unrelated heavy apps (speed up test DB setup) ───
# This prevents "Related model cannot be resolved" errors when test DB
# is created without all legacy app migrations being applied in order.
class DisableMigrations:
    """Pytest-django migration disabler — returns None for all apps so
    tests use Django's normal ORM table creation (no migration runner)."""
    def __contains__(self, item):
        return True

    def __getitem__(self, item):
        return None


MIGRATION_MODULES = DisableMigrations()

# ─── Logging — minimal noise in test output ──────────────────────────────────
LOGGING = {
    'version': 1,
    'disable_existing_loggers': True,
    'handlers': {
        'null': {'class': 'logging.NullHandler'},
    },
    'root': {
        'handlers': ['null'],
        'level': 'CRITICAL',
    },
}

# ─── SimpleJWT — token_blacklist now ENABLED ─────────────────────────────────
# AUTH_USER_MODEL migrated to 'authentication.UnifiedUser' (March 2026).
# simplejwt's OutstandingToken.user FK now correctly points to UnifiedUser.
# token_blacklist app is retained in INSTALLED_APPS — no workaround needed.

SIMPLE_JWT = {
    **SIMPLE_JWT,           # type: ignore[name-defined]
    'ROTATE_REFRESH_TOKENS': False,
    'BLACKLIST_AFTER_ROTATION': False,
    'UPDATE_LAST_LOGIN': False,
}

from django.db.backends.signals import connection_created
from django.dispatch import receiver

@receiver(connection_created)
def set_sqlite_pragma(sender, connection, **kwargs):
    if connection.vendor == 'sqlite':
        cursor = connection.cursor()
        cursor.execute('PRAGMA journal_mode=WAL;')
        cursor.execute('PRAGMA synchronous=NORMAL;')
