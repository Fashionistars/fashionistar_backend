# backend/config/logging_config.py
"""
FASHIONISTAR — Enterprise Per-App Logging Configuration
=========================================================

Architecture:
  ┌──────────────────────────────────────────────────────────────────┐
  │            Fashionistar Logging Architecture v2.0                │
  │                                                                  │
  │  LOGGER NAMES               LOG FILE                            │
  │  ─────────────────────────  ──────────────────────────────────  │
  │  apps.authentication.*   →  logs/apps/authentication/auth.log   │
  │  apps.common.*           →  logs/apps/common/common.log         │
  │  apps.store.*            →  logs/apps/store/store.log           │
  │  apps.customer (legacy)  →  logs/apps/customer/customer.log     │
  │  apps.vendor (legacy)    →  logs/apps/vendor/vendor.log         │
  │  apps.payments.*         →  logs/apps/payments/payments.log     │
  │  apps.notifications      →  logs/apps/notifications/notify.log  │
  │  apps.chat               →  logs/apps/chat/chat.log             │
  │  admin_backend.*         →  logs/apps/admin/admin.log           │
  │  security                →  logs/system/security.log            │
  │  webhook                 →  logs/system/webhook.log             │
  │  paystack                →  logs/system/paystack.log            │
  │  permissions             →  logs/system/permissions.log         │
  │  celery                  →  logs/system/celery.log              │
  │  application (catchall)  →  logs/system/application.log        │
  │  django.*                →  logs/system/django.log              │
  │                                                                  │
  │  ALL loggers also → console (dev: DEBUG, prod: INFO)            │
  │  Errors (≥ ERROR) always → mail_admins (production only)        │
  └──────────────────────────────────────────────────────────────────┘

Log Rotation:
  - Each file: max 10 MB, keep 10 backups → 110 MB per log channel max
  - System-level logs (application, security): max 20 MB, keep 20 backups
  - Webhook / Paystack: max 50 MB, keep 30 backups (high traffic)

JSON Formatter (production):
  Produces structured JSON lines for easy ingestion by Datadog / ELK / Loki:
  {"timestamp":"…","level":"INFO","logger":"apps.authentication",
   "module":"sync_views","func":"post","line":88,"msg":"…","request_id":"…"}

Usage pattern in each module:
  # Pattern 1 – Module-level logger (recommended, auto-routes by dotted name)
  import logging
  logger = logging.getLogger(__name__)
  # → 'apps.authentication.apis.auth_views.sync_views' routes to auth.log ✓

  # Pattern 2 – Named logger (for backward compat with existing code)
  logger = logging.getLogger('apps.authentication')

  # Pattern 3 – Helper function (for quick migration)
  from backend.config.logging_config import get_app_logger
  logger = get_app_logger('authentication')
"""

import logging
import logging.handlers
import os
import sys
from pathlib import Path

# ── Resolve BASE_DIR from this file's location ─────────────────────────────
# logging_config.py lives at: backend/config/logging_config.py
# BASE_DIR (project root) is 2 levels up: fashionistar_backend/
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# ── Log directory roots ─────────────────────────────────────────────────────
LOG_ROOT = BASE_DIR / 'logs'
APPS_LOG_ROOT = LOG_ROOT / 'apps'
SYS_LOG_ROOT = LOG_ROOT / 'system'

# ── File size / rotation constants ──────────────────────────────────────────
_10MB = 10 * 1024 * 1024     # per-app standard
_20MB = 20 * 1024 * 1024     # system-wide catchall
_50MB = 50 * 1024 * 1024     # high-traffic (webhook, paystack)
_KEEP_APP = 10
_KEEP_SYS = 20
_KEEP_HIGH = 30


# =============================================================================
# FORMATTERS
# =============================================================================

class FashionistarJSONFormatter(logging.Formatter):
    """
    Structured JSON log formatter — production-ready for ELK / Loki / Datadog.

    Output per line:
      {
        "timestamp":  "2026-03-08T11:02:58+01:00",
        "level":      "INFO",
        "logger":     "apps.authentication.services.registration_service",
        "module":     "registration_service",
        "func":       "register_sync",
        "line":       88,
        "process":    12345,
        "thread":     67890,
        "msg":        "User created: id=uuid123",
        "request_id": "req-xyz"  ← from RequestIDMiddleware if present
      }
    """

    def format(self, record: logging.LogRecord) -> str:
        import json
        import datetime

        payload = {
            "timestamp": datetime.datetime.fromtimestamp(
                record.created,
                tz=datetime.timezone.utc
            ).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "module": record.module,
            "func": record.funcName,
            "line": record.lineno,
            "process": record.process,
            "thread": record.thread,
            "msg": record.getMessage(),
        }

        # Attach request_id if set by RequestIDMiddleware
        request_id = getattr(record, 'request_id', None)
        if request_id:
            payload["request_id"] = request_id

        # Attach exception info if present
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)

        if record.stack_info:
            payload["stack_info"] = self.formatStack(record.stack_info)

        return json.dumps(payload, ensure_ascii=False)


# Pre-built formatter instances (referenced by handler dicts below)
_VERBOSE_FMT = (
    '[{levelname:8}] {asctime} | {name}:{lineno} | '
    'PID:{process} | {funcName}() | {message}'
)
_SIMPLE_FMT = '[{levelname:8}] {name} — {message}'
_CONSOLE_FMT = '\033[1m[{levelname:8}]\033[0m {asctime} {name} — {message}'


# =============================================================================
# HELPER — create a RotatingFileHandler cleanly
# =============================================================================

def _make_file_handler(
    log_path: Path,
    level: int = logging.DEBUG,
    max_bytes: int = _10MB,
    backup_count: int = _KEEP_APP,
    use_json: bool = False,
) -> logging.handlers.RotatingFileHandler:
    """
    Build a RotatingFileHandler.
    - Creates parent directories automatically.
    - Uses UTF-8 encoding.
    - Uses JSON or verbose formatter based on use_json flag.
    """
    log_path.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.handlers.RotatingFileHandler(
        filename=str(log_path),
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding='utf-8',
    )
    handler.setLevel(level)
    if use_json:
        handler.setFormatter(FashionistarJSONFormatter())
    else:
        handler.setFormatter(
            logging.Formatter(_VERBOSE_FMT, style='{', datefmt='%Y-%m-%d %H:%M:%S')
        )
    return handler


def _make_console_handler(level: int = logging.DEBUG) -> logging.StreamHandler:
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)
    handler.setFormatter(
        logging.Formatter(_SIMPLE_FMT, style='{', datefmt='%H:%M:%S')
    )
    return handler


# =============================================================================
# PUBLIC DICT — Django LOGGING setting
# =============================================================================

def build_logging_config(
    debug: bool = True,
    use_json: bool = False,
    mail_admins: bool = False,
) -> dict:
    """
    Build and return the complete Django LOGGING dictionary.

    Args:
        debug:        True in development (DEBUG=True). Console level = DEBUG.
        use_json:     True in production → JSON formatter on file handlers.
        mail_admins:  True in production → AdminEmailHandler on ERROR.

    Returns:
        dict: Ready to assign to ``LOGGING`` in settings.

    Example (base.py):
        from backend.config.logging_config import build_logging_config
        LOGGING = build_logging_config(debug=DEBUG)

    Example (production.py):
        LOGGING = build_logging_config(debug=False, use_json=True, mail_admins=True)
    """

    console_level = 'DEBUG' if debug else 'INFO'
    file_level    = 'DEBUG' if debug else 'INFO'

    # Shared filter
    filters = {
        'require_debug_false': {
            '()': 'django.utils.log.RequireDebugFalse',
        },
        'require_debug_true': {
            '()': 'django.utils.log.RequireDebugTrue',
        },
    }

    # ── Formatters ────────────────────────────────────────────────────────────
    formatters = {
        'verbose': {
            'format': _VERBOSE_FMT,
            'style': '{',
            'datefmt': '%Y-%m-%d %H:%M:%S',
        },
        'simple': {
            'format': _SIMPLE_FMT,
            'style': '{',
            'datefmt': '%H:%M:%S',
        },
        'json': {
            '()': 'backend.config.logging_config.FashionistarJSONFormatter',
        },
    }

    active_fmt = 'json' if use_json else 'verbose'

    # ── Handlers ──────────────────────────────────────────────────────────────
    handlers: dict = {
        # ── Console ────────────────────────────────────────────────────────
        'console': {
            'class': 'logging.StreamHandler',
            'level': console_level,
            'formatter': 'simple',
            'stream': 'ext://sys.stdout',
        },

        # ── Per-App File Handlers ──────────────────────────────────────────

        # apps.authentication → logs/apps/authentication/auth.log
        'file.authentication': {
            'class': 'logging.handlers.RotatingFileHandler',
            'level': file_level,
            'formatter': active_fmt,
            'filename': str(APPS_LOG_ROOT / 'authentication' / 'auth.log'),
            'maxBytes': _10MB,
            'backupCount': _KEEP_APP,
            'encoding': 'utf-8',
        },

        # apps.common → logs/apps/common/common.log
        'file.common': {
            'class': 'logging.handlers.RotatingFileHandler',
            'level': file_level,
            'formatter': active_fmt,
            'filename': str(APPS_LOG_ROOT / 'common' / 'common.log'),
            'maxBytes': _10MB,
            'backupCount': _KEEP_APP,
            'encoding': 'utf-8',
        },

        # store / ShopCart / checkout / createOrder → logs/apps/store/store.log
        'file.store': {
            'class': 'logging.handlers.RotatingFileHandler',
            'level': file_level,
            'formatter': active_fmt,
            'filename': str(APPS_LOG_ROOT / 'store' / 'store.log'),
            'maxBytes': _10MB,
            'backupCount': _KEEP_APP,
            'encoding': 'utf-8',
        },

        # customer / measurements / addon → logs/apps/customer/customer.log
        'file.customer': {
            'class': 'logging.handlers.RotatingFileHandler',
            'level': file_level,
            'formatter': active_fmt,
            'filename': str(APPS_LOG_ROOT / 'customer' / 'customer.log'),
            'maxBytes': _10MB,
            'backupCount': _KEEP_APP,
            'encoding': 'utf-8',
        },

        # vendor → logs/apps/vendor/vendor.log
        'file.vendor': {
            'class': 'logging.handlers.RotatingFileHandler',
            'level': file_level,
            'formatter': active_fmt,
            'filename': str(APPS_LOG_ROOT / 'vendor' / 'vendor.log'),
            'maxBytes': _10MB,
            'backupCount': _KEEP_APP,
            'encoding': 'utf-8',
        },

        # Paystack (payments) → logs/apps/payments/payments.log
        'file.payments': {
            'class': 'logging.handlers.RotatingFileHandler',
            'level': file_level,
            'formatter': active_fmt,
            'filename': str(APPS_LOG_ROOT / 'payments' / 'payments.log'),
            'maxBytes': _50MB,
            'backupCount': _KEEP_HIGH,
            'encoding': 'utf-8',
        },

        # notification / chat → logs/apps/notifications/notify.log
        'file.notifications': {
            'class': 'logging.handlers.RotatingFileHandler',
            'level': file_level,
            'formatter': active_fmt,
            'filename': str(APPS_LOG_ROOT / 'notifications' / 'notify.log'),
            'maxBytes': _10MB,
            'backupCount': _KEEP_APP,
            'encoding': 'utf-8',
        },

        # chat → logs/apps/chat/chat.log
        'file.chat': {
            'class': 'logging.handlers.RotatingFileHandler',
            'level': file_level,
            'formatter': active_fmt,
            'filename': str(APPS_LOG_ROOT / 'chat' / 'chat.log'),
            'maxBytes': _10MB,
            'backupCount': _KEEP_APP,
            'encoding': 'utf-8',
        },

        # admin_backend → logs/apps/admin/admin.log
        'file.admin': {
            'class': 'logging.handlers.RotatingFileHandler',
            'level': file_level,
            'formatter': active_fmt,
            'filename': str(APPS_LOG_ROOT / 'admin' / 'admin.log'),
            'maxBytes': _10MB,
            'backupCount': _KEEP_APP,
            'encoding': 'utf-8',
        },

        # ── System-Level File Handlers ─────────────────────────────────────

        # security events (auth failures, suspicious IPs)
        'file.security': {
            'class': 'logging.handlers.RotatingFileHandler',
            'level': 'INFO',   # Always INFO — never suppress security events
            'formatter': active_fmt,
            'filename': str(SYS_LOG_ROOT / 'security.log'),
            'maxBytes': _20MB,
            'backupCount': _KEEP_SYS,
            'encoding': 'utf-8',
        },

        # Paystack webhook events (raw HTTP payloads)
        'file.webhook': {
            'class': 'logging.handlers.RotatingFileHandler',
            'level': 'INFO',
            'formatter': active_fmt,
            'filename': str(SYS_LOG_ROOT / 'webhook.log'),
            'maxBytes': _50MB,
            'backupCount': _KEEP_HIGH,
            'encoding': 'utf-8',
        },

        # Paystack API calls (charges, transfers, verifications)
        'file.paystack': {
            'class': 'logging.handlers.RotatingFileHandler',
            'level': 'INFO',
            'formatter': active_fmt,
            'filename': str(SYS_LOG_ROOT / 'paystack.log'),
            'maxBytes': _50MB,
            'backupCount': _KEEP_HIGH,
            'encoding': 'utf-8',
        },

        # permissions / RBAC → logs/system/permissions.log
        'file.permissions': {
            'class': 'logging.handlers.RotatingFileHandler',
            'level': 'INFO',
            'formatter': active_fmt,
            'filename': str(SYS_LOG_ROOT / 'permissions.log'),
            'maxBytes': _10MB,
            'backupCount': _KEEP_APP,
            'encoding': 'utf-8',
        },

        # Celery task lifecycle → logs/system/celery.log
        'file.celery': {
            'class': 'logging.handlers.RotatingFileHandler',
            'level': file_level,
            'formatter': active_fmt,
            'filename': str(SYS_LOG_ROOT / 'celery.log'),
            'maxBytes': _20MB,
            'backupCount': _KEEP_SYS,
            'encoding': 'utf-8',
        },

        # Django internal → logs/system/django.log
        'file.django': {
            'class': 'logging.handlers.RotatingFileHandler',
            'level': 'INFO',
            'formatter': active_fmt,
            'filename': str(SYS_LOG_ROOT / 'django.log'),
            'maxBytes': _20MB,
            'backupCount': _KEEP_SYS,
            'encoding': 'utf-8',
        },

        # Catchall: 'application' logger (legacy code) → logs/system/application.log
        'file.application': {
            'class': 'logging.handlers.RotatingFileHandler',
            'level': file_level,
            'formatter': active_fmt,
            'filename': str(SYS_LOG_ROOT / 'application.log'),
            'maxBytes': _20MB,
            'backupCount': _KEEP_SYS,
            'encoding': 'utf-8',
        },
    }

    # Add mail_admins handler in production
    if mail_admins:
        handlers['mail_admins'] = {
            'class': 'django.utils.log.AdminEmailHandler',
            'level': 'ERROR',
            'formatter': 'verbose',
            'filters': ['require_debug_false'],
        }

    def _handlers_for(*names: str) -> list:
        """Return console + named file handlers, optionally + mail_admins."""
        result = ['console'] + list(names)
        if mail_admins:
            result.append('mail_admins')
        return result

    # ── Loggers ───────────────────────────────────────────────────────────────
    loggers: dict = {

        # ── Django internals ─────────────────────────────────────────────────
        'django': {
            'handlers': _handlers_for('file.django'),
            'level': 'INFO',
            'propagate': False,
        },
        'django.request': {
            'handlers': _handlers_for('file.django'),
            'level': 'WARNING',
            'propagate': False,
        },
        'django.security': {
            'handlers': _handlers_for('file.security'),
            'level': 'INFO',
            'propagate': False,
        },
        'django.db.backends': {
            # SQL query logging — DEBUG only (never in production)
            'handlers': ['console', 'file.django'],
            'level': 'DEBUG' if debug else 'WARNING',
            'propagate': False,
        },

        # ── apps.authentication ──────────────────────────────────────────────
        'apps.authentication': {
            'handlers': _handlers_for('file.authentication'),
            'level': 'DEBUG' if debug else 'INFO',
            'propagate': False,
        },

        # ── apps.common ──────────────────────────────────────────────────────
        'apps.common': {
            'handlers': _handlers_for('file.common'),
            'level': 'DEBUG' if debug else 'INFO',
            'propagate': False,
        },

        # ── Store domain (new + legacy) ───────────────────────────────────────
        'apps.store': {
            'handlers': _handlers_for('file.store'),
            'level': 'DEBUG' if debug else 'INFO',
            'propagate': False,
        },
        'store': {
            'handlers': _handlers_for('file.store'),
            'level': 'DEBUG' if debug else 'INFO',
            'propagate': False,
        },
        'ShopCart': {
            'handlers': _handlers_for('file.store'),
            'level': 'DEBUG' if debug else 'INFO',
            'propagate': False,
        },
        'checkout': {
            'handlers': _handlers_for('file.store'),
            'level': 'DEBUG' if debug else 'INFO',
            'propagate': False,
        },
        'createOrder': {
            'handlers': _handlers_for('file.store'),
            'level': 'DEBUG' if debug else 'INFO',
            'propagate': False,
        },
        'Homepage': {
            'handlers': _handlers_for('file.store'),
            'level': 'DEBUG' if debug else 'INFO',
            'propagate': False,
        },
        'addon': {
            'handlers': _handlers_for('file.store'),
            'level': 'DEBUG' if debug else 'INFO',
            'propagate': False,
        },

        # ── Customer domain ───────────────────────────────────────────────────
        'apps.customer': {
            'handlers': _handlers_for('file.customer'),
            'level': 'DEBUG' if debug else 'INFO',
            'propagate': False,
        },
        'customer': {
            'handlers': _handlers_for('file.customer'),
            'level': 'DEBUG' if debug else 'INFO',
            'propagate': False,
        },
        'measurements': {
            'handlers': _handlers_for('file.customer'),
            'level': 'DEBUG' if debug else 'INFO',
            'propagate': False,
        },

        # ── Vendor domain ─────────────────────────────────────────────────────
        'apps.vendor': {
            'handlers': _handlers_for('file.vendor'),
            'level': 'DEBUG' if debug else 'INFO',
            'propagate': False,
        },
        'vendor': {
            'handlers': _handlers_for('file.vendor'),
            'level': 'DEBUG' if debug else 'INFO',
            'propagate': False,
        },

        # ── Payments (Paystack) ───────────────────────────────────────────────
        'apps.payments': {
            'handlers': _handlers_for('file.payments'),
            'level': 'DEBUG' if debug else 'INFO',
            'propagate': False,
        },
        'Paystack_Webhoook_Prod': {
            'handlers': _handlers_for('file.payments'),
            'level': 'DEBUG' if debug else 'INFO',
            'propagate': False,
        },
        'paystack': {
            'handlers': _handlers_for('file.paystack'),
            'level': 'INFO',    # Always INFO — financial audit trail
            'propagate': False,
        },

        # ── Webhook ───────────────────────────────────────────────────────────
        'webhook': {
            'handlers': _handlers_for('file.webhook'),
            'level': 'INFO',    # Always INFO — financial audit trail
            'propagate': False,
        },

        # ── Notifications / Chat ──────────────────────────────────────────────
        'apps.notifications': {
            'handlers': _handlers_for('file.notifications'),
            'level': 'DEBUG' if debug else 'INFO',
            'propagate': False,
        },
        'notification': {
            'handlers': _handlers_for('file.notifications'),
            'level': 'DEBUG' if debug else 'INFO',
            'propagate': False,
        },
        'Blog': {
            'handlers': _handlers_for('file.notifications'),
            'level': 'DEBUG' if debug else 'INFO',
            'propagate': False,
        },
        'chat': {
            'handlers': _handlers_for('file.chat'),
            'level': 'DEBUG' if debug else 'INFO',
            'propagate': False,
        },

        # ── Admin ─────────────────────────────────────────────────────────────
        'admin_backend': {
            'handlers': _handlers_for('file.admin'),
            'level': 'DEBUG' if debug else 'INFO',
            'propagate': False,
        },
        'userauths': {
            'handlers': _handlers_for('file.admin'),
            'level': 'DEBUG' if debug else 'INFO',
            'propagate': False,
        },
        'utilities': {
            'handlers': _handlers_for('file.admin'),
            'level': 'DEBUG' if debug else 'INFO',
            'propagate': False,
        },
        'api': {
            'handlers': _handlers_for('file.admin'),
            'level': 'DEBUG' if debug else 'INFO',
            'propagate': False,
        },

        # ── System ────────────────────────────────────────────────────────────
        'security': {
            'handlers': _handlers_for('file.security'),
            'level': 'INFO',    # Always INFO — SIEM/CERT audit trail
            'propagate': False,
        },
        'permissions': {
            'handlers': _handlers_for('file.permissions'),
            'level': 'INFO',
            'propagate': False,
        },
        'celery': {
            'handlers': _handlers_for('file.celery'),
            'level': 'DEBUG' if debug else 'INFO',
            'propagate': False,
        },
        'celery.task': {
            'handlers': _handlers_for('file.celery'),
            'level': 'DEBUG' if debug else 'INFO',
            'propagate': False,
        },
        'celery.worker': {
            'handlers': _handlers_for('file.celery'),
            'level': 'INFO',
            'propagate': False,
        },

        # ── Catchall: legacy 'application' logger ─────────────────────────────
        # All existing code using getLogger('application') continues to work.
        # Gradually migrate modules to getLogger(__name__) for per-app routing.
        'application': {
            'handlers': _handlers_for('file.application'),
            'level': 'DEBUG' if debug else 'INFO',
            'propagate': False,
        },
    }

    return {
        'version': 1,
        'disable_existing_loggers': False,
        'filters': filters,
        'formatters': formatters,
        'handlers': handlers,
        'loggers': loggers,
    }


# =============================================================================
# HELPER — get_app_logger
# =============================================================================

def get_app_logger(app_name: str) -> logging.Logger:
    """
    Convenience helper for getting the correct named logger for an app.

    Translates short names → dotted logger names that route to the right file.

    Args:
        app_name: Short app name ('authentication', 'common', 'store', etc.)

    Returns:
        logging.Logger: Named logger, auto-routed to the right log file.

    Usage:
        from backend.config.logging_config import get_app_logger
        logger = get_app_logger('authentication')
        # equivalent to: logging.getLogger('apps.authentication')
        # → writes to logs/apps/authentication/auth.log

    Migration guide for existing code:
        Old:  logger = logging.getLogger('application')
        New:  logger = get_app_logger('authentication')  # or 'common', etc.
              # OR (better):
              logger = logging.getLogger(__name__)
              # Django's logger hierarchy auto-routes to the correct file!
    """
    _APP_MAP = {
        'authentication': 'apps.authentication',
        'auth':           'apps.authentication',
        'common':         'apps.common',
        'store':          'apps.store',
        'customer':       'apps.customer',
        'vendor':         'apps.vendor',
        'payments':       'apps.payments',
        'paystack':       'paystack',
        'webhook':        'webhook',
        'notifications':  'apps.notifications',
        'notification':   'notification',
        'chat':           'chat',
        'admin':          'admin_backend',
        'security':       'security',
        'permissions':    'permissions',
        'celery':         'celery',
        'application':    'application',
    }
    logger_name = _APP_MAP.get(app_name.lower(), f'apps.{app_name.lower()}')
    return logging.getLogger(logger_name)


# =============================================================================
# ENSURE ALL LOG DIRECTORIES EXIST AT IMPORT TIME
# =============================================================================

def ensure_log_directories() -> None:
    """
    Create all log directories and subdirectories.
    Called at app startup from apps/common/apps.py or settings.

    Idempotent: safe to call multiple times.
    """
    dirs = [
        APPS_LOG_ROOT / 'authentication',
        APPS_LOG_ROOT / 'common',
        APPS_LOG_ROOT / 'store',
        APPS_LOG_ROOT / 'customer',
        APPS_LOG_ROOT / 'vendor',
        APPS_LOG_ROOT / 'payments',
        APPS_LOG_ROOT / 'notifications',
        APPS_LOG_ROOT / 'chat',
        APPS_LOG_ROOT / 'admin',
        SYS_LOG_ROOT,
    ]
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)


# Call at module import — so directories exist before Django starts logging
ensure_log_directories()
