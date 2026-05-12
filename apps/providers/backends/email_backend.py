# apps/providers/backends/email_backend.py
"""
DatabaseConfiguredEmailBackend — production Django email backend.

Reads the active backend path from EmailProviderConfig (providers registry)
and delegates every email dispatch to the resolved backend class.

Set in settings:
    EMAIL_BACKEND = "apps.providers.backends.email_backend.DatabaseConfiguredEmailBackend"

Cache behaviour:
    Warm reads are served from Redis (5-min TTL via apps.providers.cache).
    Cold starts or cache misses hit the DB once then re-populate the cache.
"""
from __future__ import annotations

import logging
from django.apps import apps
from django.core.mail.backends.base import BaseEmailBackend
from django.utils.module_loading import import_string

from apps.providers.cache import get_email_provider_config

application_logger = logging.getLogger("application")


class DatabaseConfiguredEmailBackend(BaseEmailBackend):
    """
    Dynamic email backend that loads the active provider from the registry.

    Fallback chain:
        1. EmailProviderConfig (DB + Redis cache)
        2. SMTP backend (always available, no third-party dependency)
    """

    _FALLBACK_BACKEND = "django.core.mail.backends.smtp.EmailBackend"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.email_backend = self._load_backend(*args, **kwargs)

    def _load_backend(self, *args, **kwargs) -> BaseEmailBackend:
        try:
            config = get_email_provider_config()
            backend_path = (
                config.email_backend if config else self._FALLBACK_BACKEND
            )
            application_logger.info(
                "EmailBackend: loading backend=%s", backend_path
            )
            backend_class = import_string(backend_path)
            return backend_class(*args, **kwargs)

        except ImportError as exc:
            application_logger.error(
                "EmailBackend: ImportError loading %s — %s", backend_path, exc, exc_info=True
            )
        except Exception as exc:
            application_logger.error(
                "EmailBackend: unexpected error — %s", exc, exc_info=True
            )

        # Fallback
        application_logger.warning(
            "EmailBackend: falling back to SMTP (%s)", self._FALLBACK_BACKEND
        )
        from django.core.mail.backends.smtp import EmailBackend
        return EmailBackend(*args, **kwargs)

    def send_messages(self, email_messages):
        return self.email_backend.send_messages(email_messages)
