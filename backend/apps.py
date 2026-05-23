# backend/apps.py
"""
BackendConfig — Django AppConfig for the 'backend' project package.

Fixes Python 3.12's logging QueueHandler silently dropping log records under
Uvicorn/Daphne ASGI servers. Handles all known edge cases:

  - Django StatReloader calls ready() TWICE (parent + child process) → guard
  - django.utils.autoreload floods terminal with DEBUG site-packages dirs → suppress
  - Celery worker hijacks root logger AFTER ready() → skip root StreamHandler
    in worker mode and let Celery's own logging handle console output
"""

import logging
import logging.handlers
import os
import sys
from pathlib import Path

from django.apps import AppConfig

# Module-level flag to prevent double-init from Django's StatReloader.
# The autoreloader spawns a child process; ready() fires in both parent + child.
# We use an env var (persists across the exec() boundary) to detect the child.
_BACKEND_LOGGING_READY_ENV = 'FASHIONISTAR_LOGGING_READY'


def _is_celery_worker() -> bool:
    """
    Detect if we are running inside a Celery worker process.

    Celery worker invocation: `celery -A backend.celery worker ...`
    sys.argv[0] ends with 'celery' and 'worker' is in the args.
    Also handles Windows where argv[0] might be the full path.
    """
    argv = ' '.join(sys.argv).lower()
    return 'celery' in argv and ('worker' in argv or 'beat' in argv)


class BackendConfig(AppConfig):
    name = 'backend'
    verbose_name = 'Backend Core'

    def ready(self):
        """
        Configure logging ONCE after all Django apps are fully loaded.

        Guards:
          - Idempotent: env var prevents double-run on StatReloader restart
          - Celery-aware: skips root StreamHandler in worker mode (Celery owns
            the root logger in worker mode via celeryd_hijack_root_logger)
        """
        _BASE = Path(__file__).resolve().parent.parent

        # ── Guard: StatReloader calls ready() in parent AND child process ────
        # We use an env var so the guard persists across the os.exec() call
        # that the autoreloader uses to restart the child process.
        already_ran = os.environ.get(_BACKEND_LOGGING_READY_ENV)
        os.environ[_BACKEND_LOGGING_READY_ENV] = '1'

        in_celery_worker = _is_celery_worker()

        # ── Step 1: Wipe all existing root handlers ──────────────────────────
        # dictConfig() placed a QueueHandler (with no listener) on root.
        # Clear it before we install our own handler to avoid duplicates.
        root = logging.getLogger()
        for handler in list(root.handlers):
            try:
                if hasattr(handler, 'listener') and handler.listener is not None:
                    handler.listener.stop()
            except Exception:
                pass
            root.removeHandler(handler)

        # ── Step 2: Silence django.utils.autoreload DEBUG spam ───────────────
        # The autoreloader logs a DEBUG line for EVERY template/locale dir it
        # watches (including hundreds of venv/site-packages dirs). Set it to
        # WARNING so only real problems appear.
        logging.getLogger('django.utils.autoreload').setLevel(logging.WARNING)

        # ── Step 3: Console StreamHandler — skip in Celery worker mode ───────
        # In Celery worker mode, Celery's own signal handler
        # (celeryd_hijack_root_logger) adds its `[timestamp: LEVEL/Process]`
        # format handler to root AFTER ready() runs. If we also add our
        # StreamHandler to root, every record appears in TWO formats.
        # Solution: in worker mode, trust Celery's own logging; only add file
        # handlers for persistence.
        console_fmt = logging.Formatter(
            '[%(levelname)-8s] %(name)s \u2014 %(message)s'
        )
        if not in_celery_worker:
            sh = logging.StreamHandler(sys.stdout)
            sh.setFormatter(console_fmt)
            sh.setLevel(logging.DEBUG)
            root.addHandler(sh)
            root.setLevel(logging.DEBUG)
        else:
            # Celery worker: let Celery control root. Just set the level.
            root.setLevel(logging.DEBUG)

        # ── Step 4: Per-app RotatingFileHandler + propagation ────────────────
        file_fmt = logging.Formatter(
            '[%(levelname)-8s] %(asctime)s | %(name)s:%(lineno)d | '
            '%(funcName)s() | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S',
        )

        log_map = {
            'apps.authentication': 'logs/apps/authentication/auth.log',
            'apps.common':         'logs/apps/common/common.log',
            'apps.audit_logs':     'logs/apps/audit_logs/audit_logs.log',
            'apps.store':          'logs/apps/store/store.log',
            'apps.customer':       'logs/apps/customer/customer.log',
            'apps.client':         'logs/apps/client/client.log',
            'apps.vendor':         'logs/apps/vendor/vendor.log',
            'apps.payments':       'logs/apps/payments/payments.log',
            'apps.transactions':   'logs/apps/transactions/transactions.log',
            'apps.wallet':         'logs/apps/wallet/wallet.log',
            'apps.product':        'logs/apps/product/product.log',
            'apps.catalog':        'logs/apps/catalog/catalog.log',
            'apps.cart':           'logs/apps/cart/cart.log',
            'apps.order':          'logs/apps/order/order.log',
            'apps.chat':           'logs/apps/chat/chat.log',
            'apps.support':        'logs/apps/support/support.log',
            'apps.notification':   'logs/apps/notification/notification.log',
            'apps.measurements':   'logs/apps/measurements/measurements.log',
            'apps.kyc':            'logs/apps/kyc/kyc.log',
            'apps.providers':      'logs/apps/providers/providers.log',
            'celery':              'logs/system/celery.log',
            'celery.task':         'logs/system/celery.log',
            'django':              'logs/system/django.log',
            'apps.global_platform_settings':            'logs/apps/global_platform_settings/global_platform_settings.log',

        }

        for name, rel_path in log_map.items():
            lg = logging.getLogger(name)

            # Remove any stale handlers placed by dictConfig
            for h in list(lg.handlers):
                lg.removeHandler(h)

            # File handler — always active (dev server, Uvicorn, Daphne, Celery)
            from backend.config.logging_config import SafeRotatingFileHandler, get_log_suffix
            suffix = get_log_suffix()
            log_path = _BASE / rel_path
            if suffix:
                log_path = log_path.with_name(f"{log_path.stem}{suffix}{log_path.suffix}")
            log_path.parent.mkdir(parents=True, exist_ok=True)
            try:
                fh = SafeRotatingFileHandler(
                    filename=str(log_path),
                    maxBytes=10 * 1024 * 1024,
                    backupCount=10,
                    encoding='utf-8',
                )
            except Exception as e:
                sys.stderr.write(f"[BackendConfig] Could not create file handler for {name} on Windows: {e}\n")
                sys.stderr.flush()
                continue
            fh.setFormatter(file_fmt)
            fh.setLevel(logging.DEBUG)
            lg.addHandler(fh)

            # propagate=True lets records reach root StreamHandler (console)
            # In Celery worker mode, root has Celery's handler — still correct.
            lg.propagate = True
            lg.setLevel(logging.DEBUG)

        # ── Step 5: Print startup message — only ONCE, only in non-Celery ────
        if not already_ran and not in_celery_worker:
            server = 'ASGI' if 'uvicorn' in argv_str() else 'Django dev'
            print(
                f'[BackendConfig] {server} logging ready: '
                'StreamHandler on root, per-app file handlers, '
                'autoreload DEBUG suppressed.',
                flush=True,
            )
        elif not already_ran and in_celery_worker:
            from backend.config.logging_config import get_log_suffix
            suffix = get_log_suffix()
            print(
                f'[BackendConfig] Celery worker logging ready (suffix="{suffix}"): '
                'per-app file handlers only (Celery owns root console).',
                flush=True,
            )

        # ── Step 6: Monkey-patch URLResolver to have a 'name' property ────────
        # Django's template engine, particularly during technical 404 views,
        # loops through `tried` patterns (which contain both URLPatterns and
        # URLResolvers). It looks up pattern.name, which causes AttributeError
        # and floods logs with VariableDoesNotExist exceptions on URLResolver.
        try:
            from django.urls.resolvers import URLResolver
            if not hasattr(URLResolver, 'name'):
                @property
                def resolver_name(self):
                    return None
                URLResolver.name = resolver_name
        except Exception as e:
            sys.stderr.write(f"[BackendConfig] Could not patch URLResolver: {e}\n")
            sys.stderr.flush()


def argv_str() -> str:
    """Return joined sys.argv as a single lowercase string for easy checks."""
    return ' '.join(sys.argv).lower()
