# backend/apps.py
"""
BackendConfig — Django AppConfig for the 'backend' project package.

Fixes Python 3.12's logging QueueHandler silently dropping log records under
Uvicorn/Daphne ASGI servers, and prevents duplicate log lines.

ROOT CAUSE (Python 3.12 + Django ASGI)
=======================================
Django's LOGGING_CONFIG calls logging.config.dictConfig() during setup().
In Python 3.12, dictConfig() wraps EVERY configured handler in a QueueHandler.
The QueueListener backing thread is not started correctly under Uvicorn/Daphne,
so initially logs are dropped. When we naively add a StreamHandler to root in
ready(), we end up with THREE handlers all writing to stdout:

  1. QueueHandler (on root) → QueueListener → stdout  (verbose format)
  2. StreamHandler (on root, added by us)              (short format)
  3. RotatingFileHandler (per app) propagates to root  (double-counted)

Result: each log line prints 2–3 times.

THE FIX
=======
In ready():
  1. CLEAR all existing root handlers (removes the QueueHandler + its listener)
  2. Add exactly ONE direct StreamHandler(stdout) to root
  3. Set propagate=True on app loggers so they reach root → stdout
  4. Add RotatingFileHandler directly to each app logger (propagate=True means
     records go to BOTH the file handler AND root StreamHandler — once each)
"""

import logging
import logging.handlers
import sys
from pathlib import Path

from django.apps import AppConfig


class BackendConfig(AppConfig):
    name = 'backend'
    verbose_name = 'Backend Core'

    def ready(self):
        """
        Replace Python 3.12's broken QueueHandler setup with a clean,
        direct logging configuration that works on all server types.

        Called once by Django after all apps are fully loaded.
        """
        _BASE = Path(__file__).resolve().parent.parent

        # ── Step 1: Wipe all existing root handlers ───────────────────────────
        # dictConfig() put a QueueHandler (and potentially a listener) on root.
        # If we just ADD to root we get duplicates. Clear first, then rebuild.
        root = logging.getLogger()
        for handler in list(root.handlers):
            try:
                # Cleanly stop any QueueListener attached to a QueueHandler
                if hasattr(handler, 'listener') and handler.listener is not None:
                    handler.listener.stop()
            except Exception:
                pass
            root.removeHandler(handler)

        # ── Step 2: Add ONE StreamHandler to root ─────────────────────────────
        # All app loggers with propagate=True will route records here exactly once.
        console_fmt = logging.Formatter(
            '[%(levelname)-8s] %(name)s \u2014 %(message)s'
        )
        sh = logging.StreamHandler(sys.stdout)
        sh.setFormatter(console_fmt)
        sh.setLevel(logging.DEBUG)
        root.addHandler(sh)
        root.setLevel(logging.DEBUG)

        # ── Step 3: Configure per-app loggers ─────────────────────────────────
        # propagate=True  → record goes to root StreamHandler (console) once.
        # No StreamHandler on the per-app logger itself → no double-print.
        # A RotatingFileHandler is added directly for file persistence.
        file_fmt = logging.Formatter(
            '[%(levelname)-8s] %(asctime)s | %(name)s:%(lineno)d | '
            '%(funcName)s() | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S',
        )

        log_map = {
            'apps.authentication': 'logs/apps/authentication/auth.log',
            'apps.common':         'logs/apps/common/common.log',
            'apps.store':          'logs/apps/store/store.log',
            'apps.customer':       'logs/apps/customer/customer.log',
            'apps.vendor':         'logs/apps/vendor/vendor.log',
            'apps.payments':       'logs/apps/payments/payments.log',
            'celery':              'logs/system/celery.log',
            'celery.task':         'logs/system/celery.log',
            'django':              'logs/system/django.log',
        }

        for name, rel_path in log_map.items():
            lg = logging.getLogger(name)

            # Remove any handlers placed by dictConfig to avoid duplicates
            for h in list(lg.handlers):
                lg.removeHandler(h)

            # File handler (writes to per-app rotating log file)
            log_path = _BASE / rel_path
            log_path.parent.mkdir(parents=True, exist_ok=True)
            fh = logging.handlers.RotatingFileHandler(
                filename=str(log_path),
                maxBytes=10 * 1024 * 1024,   # 10 MB
                backupCount=10,
                encoding='utf-8',
            )
            fh.setFormatter(file_fmt)
            fh.setLevel(logging.DEBUG)
            lg.addHandler(fh)

            # Allow records to bubble up to root (→ console StreamHandler)
            lg.propagate = True
            lg.setLevel(logging.DEBUG)

        print(
            '[BackendConfig] Logging ready: 1x StreamHandler on root, '
            'per-app RotatingFileHandlers attached, propagation enabled.',
            flush=True,
        )
