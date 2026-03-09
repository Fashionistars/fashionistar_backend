# backend/apps.py
"""
BackendConfig — Django AppConfig for the 'backend' project package.

Ensures Python 3.12's logging QueueHandler does not silently
swallow log records under Uvicorn / Daphne ASGI servers.
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
        Guarantee console logging works on ALL server types by directly
        patching logging.root after Django finishes loading all apps.

        WHY:
        Python 3.12's logging.config.dictConfig() wraps every configured
        handler in a QueueHandler. The QueueListener backing thread must be
        started explicitly; under Uvicorn/Daphne, it is never started
        correctly, so ALL log records are silently dropped.

        FIX:
        We add a raw StreamHandler(stdout) directly to the ROOT logger.
        Every logger that uses propagate=True will then route records here.
        We also set propagate=True on any app loggers that dictConfig set to
        False, so they now reach root and thus stdout.
        """
        _BASE = Path(__file__).resolve().parent.parent

        console_fmt = logging.Formatter(
            '[%(levelname)-8s] %(name)s - %(message)s'
        )

        # -- Add a direct StreamHandler to root (bypasses QueueHandler) --------
        root = logging.getLogger()
        has_stream = any(
            isinstance(h, logging.StreamHandler)
            and not isinstance(h, logging.FileHandler)
            for h in root.handlers
        )
        if not has_stream:
            sh = logging.StreamHandler(sys.stdout)
            sh.setFormatter(console_fmt)
            sh.setLevel(logging.DEBUG)
            root.addHandler(sh)
            root.setLevel(logging.DEBUG)

        # -- Ensure app loggers propagate to root so they reach the handler ----
        app_logger_names = [
            'apps.authentication',
            'apps.common',
            'apps.store',
            'apps.customer',
            'apps.vendor',
            'apps.payments',
            'celery',
            'celery.task',
            'django',
        ]
        for name in app_logger_names:
            lg = logging.getLogger(name)
            lg.propagate = True           # let records bubble up to root
            if lg.level == 0 or lg.level > logging.DEBUG:
                lg.setLevel(logging.DEBUG)

        # -- Also add per-app rotating file handlers directly ------------------
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
            'django':              'logs/system/django.log',
        }
        for name, rel_path in log_map.items():
            lg = logging.getLogger(name)
            has_fh = any(isinstance(h, logging.FileHandler) for h in lg.handlers)
            if not has_fh:
                log_path = _BASE / rel_path
                log_path.parent.mkdir(parents=True, exist_ok=True)
                fh = logging.handlers.RotatingFileHandler(
                    filename=str(log_path),
                    maxBytes=10 * 1024 * 1024,
                    backupCount=10,
                    encoding='utf-8',
                )
                fh.setFormatter(file_fmt)
                fh.setLevel(logging.DEBUG)
                lg.addHandler(fh)

        print(
            '[BackendConfig] Logging patched: StreamHandler on root, '
            'file handlers on app loggers, propagate=True set.',
            flush=True,
        )
