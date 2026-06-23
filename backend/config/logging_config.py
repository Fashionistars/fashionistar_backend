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
  │  apps.client (legacy)  →  logs/apps/client/client.log     │
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
# LOG SUFFIX DETECTION (PROCESS-SPECIFIC ISOLATION FOR WINDOWS)
# =============================================================================

def get_log_suffix() -> str:
    """
    Detect if the current process is Celery, Celery Beat, or a Django management
    command (excluding runserver), and return a suffix to isolate log files.
    This avoids Windows WinError 32 file-lock issues during rotation.
    """
    argv = ' '.join(sys.argv).lower()
    if 'celery' in argv:
        if 'beat' in argv:
            return '-beat'
        return '-celery'
    if 'manage.py' in argv and 'runserver' not in argv:
        return '-cmd'
    return ''


# =============================================================================
# SAFE ROTATING FILE HANDLER (WINDOWS COMPATIBILITY)
# =============================================================================


class SafeRotatingFileHandler(logging.handlers.RotatingFileHandler):
    """
    A rotating file handler that catches and ignores PermissionError [WinError 32]
    during file rollover on Windows. This is common when multiple processes
    (Django, Uvicorn, Celery) are writing to the same log files.
    """
    _reported_rollover_failures: set[str] = set()

    def doRollover(self) -> None:
        try:
            if os.path.exists(self.baseFilename):
                super().doRollover()
        except (PermissionError, OSError) as e:
            # Under Windows, if another process has the log file open,
            # renaming/rotating the file will raise PermissionError [WinError 32].
            # We catch this so it doesn't crash the request or server.
            show_warning = True
            try:
                from django.conf import settings
                if settings.configured and settings.DEBUG:
                    show_warning = False
            except Exception:
                pass

            failure_key = str(self.baseFilename)

            if show_warning:
                sys.stderr.write(
                    f"[SafeRotatingFileHandler] Rollover failed (file locked on Windows): {e}\n"
                )
                sys.stderr.flush()
            elif failure_key not in self._reported_rollover_failures:
                # In development we suppress repeated rollover spam and only
                # surface the first occurrence per process, so hot reloads and
                # Celery task bursts do not flood the terminal.
                self._reported_rollover_failures.add(failure_key)
                logging.getLogger("application").debug(
                    "[SafeRotatingFileHandler] Rollover failed (file locked on Windows): %s", e
                )



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
    # Use the Windows-safe rotating handler everywhere so the same rollover
    # behavior applies whether handlers are built directly here or instantiated
    # later via Django's LOGGING dict.
    handler = SafeRotatingFileHandler(
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
        """Return console + named file handlers, optionally + mail_admins, avoiding duplicates."""
        result = ['console']
        for name in names:
            if name != 'console' and name not in result:
                result.append(name)
        if mail_admins and 'mail_admins' not in result:
            result.append('mail_admins')
        return result

    is_celery_process = 'celery' in ' '.join(sys.argv).lower()

    def _celery_handlers_for(*names: str) -> list:
        """Return named file handlers, and conditionally console ONLY if running as a Celery process."""
        result = list(names)
        if is_celery_process:
            if 'console' not in result:
                result.insert(0, 'console')
        if mail_admins:
            if 'mail_admins' not in result:
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
        'django.template': {
            'handlers': _handlers_for('file.django'),
            'level': 'INFO',
            'propagate': False,
        },
        'django.db.backends': {
            # SQL query logging — ⚠️ DANGER: DEBUG logs full INSERT with password
            # hashes (pbkdf2_sha256$...) to the console. Never enable DEBUG here.
            # Use WARNING in dev to suppress — only WARNING+ SQL errors surface.
            # To temporarily enable SQL tracing (without passwords), set to INFO.
            'handlers': ['file.django'],  # FILE only — NEVER console
            'level': 'WARNING',           # Suppress in dev AND production
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

        # ── apps.catalog ─────────────────────────────────────────────────────
        'apps.catalog': {
            'handlers': _handlers_for('file.store'),
            'level': 'DEBUG' if debug else 'INFO',
            'propagate': False,
        },

        # ── apps.product ─────────────────────────────────────────────────────
        'apps.product': {
            'handlers': _handlers_for('file.store'),
            'level': 'DEBUG' if debug else 'INFO',
            'propagate': False,
        },

        # ── apps.client ──────────────────────────────────────────────────────
        'apps.client': {
            'handlers': _handlers_for('file.customer'),
            'level': 'DEBUG' if debug else 'INFO',
            'propagate': False,
        },

        # ── apps.custom_order ────────────────────────────────────────────────
        'apps.custom_order': {
            'handlers': _handlers_for('file.store'),
            'level': 'DEBUG' if debug else 'INFO',
            'propagate': False,
        },

        # ── apps.order ───────────────────────────────────────────────────────
        'apps.order': {
            'handlers': _handlers_for('file.store'),
            'level': 'DEBUG' if debug else 'INFO',
            'propagate': False,
        },

        # ── apps.payment ─────────────────────────────────────────────────────
        'apps.payment': {
            'handlers': _handlers_for('file.payments'),
            'level': 'DEBUG' if debug else 'INFO',
            'propagate': False,
        },

        # ── apps.notification ────────────────────────────────────────────────
        'apps.notification': {
            'handlers': _handlers_for('file.notifications'),
            'level': 'DEBUG' if debug else 'INFO',
            'propagate': False,
        },

        # ── apps.wallet ──────────────────────────────────────────────────────
        'apps.wallet': {
            'handlers': _handlers_for('file.payments'),
            'level': 'DEBUG' if debug else 'INFO',
            'propagate': False,
        },

        # ── apps.transactions ────────────────────────────────────────────────
        'apps.transactions': {
            'handlers': _handlers_for('file.payments'),
            'level': 'DEBUG' if debug else 'INFO',
            'propagate': False,
        },

        # ── apps.kyc ─────────────────────────────────────────────────────────
        'apps.kyc': {
            'handlers': _handlers_for('file.customer'),
            'level': 'DEBUG' if debug else 'INFO',
            'propagate': False,
        },

        # ── apps.providers ───────────────────────────────────────────────────
        'apps.providers': {
            'handlers': _handlers_for('file.vendor'),
            'level': 'DEBUG' if debug else 'INFO',
            'propagate': False,
        },

        # ── apps.support ─────────────────────────────────────────────────────
        'apps.support': {
            'handlers': _handlers_for('file.customer'),
            'level': 'DEBUG' if debug else 'INFO',
            'propagate': False,
        },

        # ── apps.scheduler ───────────────────────────────────────────────────
        'apps.scheduler': {
            'handlers': _celery_handlers_for('file.celery'),
            'level': 'DEBUG' if debug else 'INFO',
            'propagate': False,
        },

        # ── apps.search ──────────────────────────────────────────────────────
        'apps.search': {
            'handlers': _handlers_for('file.store'),
            'level': 'DEBUG' if debug else 'INFO',
            'propagate': False,
        },

        # ── apps.chat ────────────────────────────────────────────────────────
        'apps.chat': {
            'handlers': _handlers_for('file.chat'),
            'level': 'DEBUG' if debug else 'INFO',
            'propagate': False,
        },


        'apps.measurement': {
            'handlers': _handlers_for('file.customer'),
            'level': 'DEBUG' if debug else 'INFO',
            'propagate': False,
        },


        # ── Vendor domain (legacy / compatibility loggers) ────────────────────
        'apps.vendor': {
            'handlers': _handlers_for('file.vendor'),
            'level': 'DEBUG' if debug else 'INFO',
            'propagate': False,
        },

        # ── Payments (legacy / compatibility loggers) ─────────────────────────
        'apps.payments': {
            'handlers': _handlers_for('file.payments'),
            'level': 'DEBUG' if debug else 'INFO',
            'propagate': False,
        },

        # ── Webhook ───────────────────────────────────────────────────────────
        'webhook': {
            'handlers': _handlers_for('file.webhook'),
            'level': 'INFO',    # Always INFO — financial audit trail
            'propagate': False,
        },

        # ── Notifications / Chat (legacy / compatibility loggers) ─────────────
        'apps.notifications': {
            'handlers': _handlers_for('file.notifications'),
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

        # ── Celery & Beat loggers ─────────────────────────────────────────────
        'celery': {
            'handlers': _celery_handlers_for('file.celery'),
            'level': 'DEBUG' if debug else 'INFO',
            'propagate': False,
        },
        'celery.task': {
            'handlers': _celery_handlers_for('file.celery'),
            'level': 'DEBUG' if debug else 'INFO',
            'propagate': False,
        },
        'celery.worker': {
            'handlers': _celery_handlers_for('file.celery'),
            'level': 'INFO',
            'propagate': False,
        },
        'celery.beat': {
            'handlers': _celery_handlers_for('file.celery'),
            'level': 'INFO',
            'propagate': False,
        },
        'django_celery_beat': {
            'handlers': _celery_handlers_for('file.celery'),
            'level': 'INFO',
            'propagate': False,
        },
        'django_celery_results': {
            'handlers': _celery_handlers_for('file.celery'),
            'level': 'INFO',
            'propagate': False,
        },
        # ── Suppress noisy Celery internals (file-only, WARNING+) ─────────────
        # celery.utils.functional prints task function signatures at DEBUG.
        # These are internal lazy-object evaluations — NOT errors — pure noise.
        'celery.utils.functional': {
            'handlers': ['file.celery'],
            'level': 'WARNING',
            'propagate': False,
        },
        # ⚠️ DO NOT suppress celery.app.trace:
        # This logger emits 'Task received', 'Task succeeded', 'Task FAILED'
        # messages at INFO. Without it the Celery terminal is silent —
        # tasks appear to vanish even when they ARE running.
        'celery.app.trace': {
            'handlers': _celery_handlers_for('file.celery'),
            'level': 'INFO',   # INFO to console — shows task lifecycle
            'propagate': False,
        },
        'celery.utils': {
            'handlers': ['file.celery'],
            'level': 'WARNING',
            'propagate': False,
        },
        # Suppress kombu/amqp connection-level noise in dev terminal
        'kombu': {
            'handlers': ['file.celery'],
            'level': 'WARNING',
            'propagate': False,
        },
        'amqp': {
            'handlers': ['file.celery'],
            'level': 'WARNING',
            'propagate': False,
        },

        # ── Catchall for any unconfigured apps under 'apps.' namespace ────────
        'apps': {
            'handlers': _handlers_for('file.application'),
            'level': 'DEBUG' if debug else 'INFO',
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

        # ── Uvicorn ASGI server loggers ────────────────────────────────────────
        # Uvicorn uses its own internal loggers ('uvicorn.access', 'uvicorn.error')
        # and does NOT call Django's 'django.server' logger.
        #
        # CRITICAL: Uvicorn's access log records use OLD-STYLE % formatting:
        #   logger.info('%s - "%s %s HTTP/%s" %d', client, method, path, ver, status)
        # Our 'console' handler uses brace-style (style='{') for the formatter
        # template, but calls record.getMessage() which handles %-style args
        # correctly. The handler itself works fine.
        #
        # However, Uvicorn by default configures its own StreamHandler on
        # 'uvicorn' and 'uvicorn.access'. With propagate=False, our handlers
        # take over. With propagate=True and our handler ALSO added, we'd
        # get duplicate lines.
        #
        # Solution: override uvicorn.access with our console handler and no
        # propagation, which gives us the Uvicorn access format on stdout.
        'uvicorn': {
            'handlers': _handlers_for('console'),
            'level': 'INFO',
            'propagate': False,
        },
        'uvicorn.error': {
            'handlers': _handlers_for('console'),
            'level': 'INFO',
            'propagate': False,
        },
        'uvicorn.access': {
            'handlers': _handlers_for('console'),
            'level': 'INFO',
            'propagate': False,
        },
    }

    # Dynamic swap for SafeRotatingFileHandler to prevent WinError 32 on Windows in development/production
    suffix = get_log_suffix()
    for h_name, h_conf in handlers.items():
        if h_conf.get('class') == 'logging.handlers.RotatingFileHandler':
            h_conf['class'] = 'backend.config.logging_config.SafeRotatingFileHandler'
            if suffix and 'filename' in h_conf:
                path = Path(h_conf['filename'])
                h_conf['filename'] = str(path.with_name(f"{path.stem}{suffix}{path.suffix}"))

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


# =============================================================================
# STRUCTLOG CONFIGURATION (Phase 5 — Zero-cost JSON logging for ASGI)
# =============================================================================

def configure_structlog(debug: bool = False) -> None:
    """
    Configure structlog for the FASHIONISTAR platform.

    Produces lazily-evaluated structured JSON logs compatible with:
      - Datadog Log Management (dd.trace.id, dd.span.id auto-injection)
      - Sentry (error tracking with full context)
      - ELK Stack (Elasticsearch, Logstash, Kibana)
      - Loki (Grafana log aggregation)

    ASGI-safe: uses ``structlog.contextvars`` processors which are backed
    by Python's ``contextvars.ContextVar`` — task-scoped, not thread-scoped.

    Lazy evaluation: context is only serialized if the log entry passes the
    level filter. At 100k RPS this saves 2–5ms/request in pure CPU overhead
    vs. standard Python logging's eager string interpolation.

    Args:
        debug: True in development → PrettyConsole renderer instead of JSON.

    Call from Django's ``AppConfig.ready()`` (BackendConfig) after the
    logging system is initialized:

        from backend.config.logging_config import configure_structlog
        from django.conf import settings
        configure_structlog(debug=settings.DEBUG)

    Or call directly in settings:
        configure_structlog(debug=DEBUG)
    """
    try:
        import structlog
        import logging as _logging

        shared_processors = [
            # Inject asyncio task-local context (request_id, user_id, etc.)
            # bound via structlog.contextvars.bind_contextvars()
            structlog.contextvars.merge_contextvars,
            # Standard enrichment
            structlog.stdlib.add_log_level,
            structlog.stdlib.add_logger_name,
            structlog.processors.TimeStamper(fmt="iso"),
            # Inject Sentry/Datadog trace IDs if available
            _inject_trace_context,
        ]

        if debug:
            # Human-readable colored output for local development
            processors = shared_processors + [
                structlog.stdlib.PositionalArgumentsFormatter(),
                structlog.processors.StackInfoRenderer(),
                structlog.dev.ConsoleRenderer(colors=True),
            ]
        else:
            # Machine-readable JSON for production ingest pipelines
            processors = shared_processors + [
                structlog.stdlib.PositionalArgumentsFormatter(),
                structlog.processors.StackInfoRenderer(),
                structlog.processors.format_exc_info,
                structlog.processors.UnicodeDecoder(),
                structlog.processors.JSONRenderer(),
            ]

        structlog.configure(
            processors=processors,
            wrapper_class=structlog.make_filtering_bound_logger(
                _logging.DEBUG if debug else _logging.INFO
            ),
            context_class=dict,
            logger_factory=structlog.stdlib.LoggerFactory(),
            cache_logger_on_first_use=True,  # Thread-safe performance optimization
        )

    except ImportError:
        # structlog not installed — logging falls back to standard Python logging
        # which is already configured via build_logging_config() above.
        pass


def _inject_trace_context(logger, method, event_dict: dict) -> dict:
    """
    structlog processor: inject Datadog / OpenTelemetry trace context.

    Reads the current trace ID and span ID from the active tracer (ddtrace or
    OpenTelemetry) and injects them into every log record. This enables
    automatic log-to-trace correlation in Datadog's Log Management panel.

    If no tracer is active, this processor is a no-op (0ms overhead).

    Args:
        logger: The structlog logger instance.
        method: The log method name (e.g. 'info', 'error').
        event_dict: The current log event dict.

    Returns:
        dict: event_dict enriched with trace/span IDs.
    """
    # Datadog ddtrace integration
    try:
        from ddtrace import tracer as dd_tracer
        span = dd_tracer.current_span()
        if span:
            event_dict["dd.trace_id"] = str(span.trace_id)
            event_dict["dd.span_id"] = str(span.span_id)
            event_dict["dd.service"] = "fashionistar-backend"
            event_dict["dd.env"] = "production"
    except ImportError:
        pass

    # OpenTelemetry integration (alternative to ddtrace)
    try:
        from opentelemetry import trace as otel_trace
        span = otel_trace.get_current_span()
        ctx = span.get_span_context()
        if ctx and ctx.is_valid:
            event_dict["otel.trace_id"] = format(ctx.trace_id, "032x")
            event_dict["otel.span_id"] = format(ctx.span_id, "016x")
    except ImportError:
        pass

    return event_dict
