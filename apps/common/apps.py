"""
App configuration for the common app.

This module defines the configuration for the 'common' Django app,
which provides shared utilities, models, and permissions across the
project.

The ``ready()`` hook connects the analytics signal handlers from
``apps.common.signals``.

NOTE: Async logging (QueueHandler/QueueListener) was previously set up
here, but has been moved to ``backend.apps.BackendConfig.ready()`` which
runs first and configures all logging in a way that works correctly across
Django dev server, Uvicorn, Daphne, and Celery (fixing Python 3.12's
QueueHandler/QueueListener startup race condition under ASGI).
"""

import logging

from django.apps import AppConfig


class CommonConfig(AppConfig):
    """
    Configuration class for the common app.

    ``ready()`` imports ``apps.common.signals`` so that the
    ``post_save`` / ``post_delete`` handlers are connected as
    soon as the Django registry is fully loaded. Without this
    the signal receivers would never be registered.

    Attributes:
        default_auto_field (str): Default auto field type.
        name (str): App name as used in Django settings.
        verbose_name (str): Human-readable name.
    """

    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.common'
    verbose_name = 'Common Utilities'

    def ready(self):
        """
        Wire signal receivers.
        Logging is configured by BackendConfig.ready() in backend/apps.py.
        """
        # Connect analytics signal receivers
        import apps.common.signals  # noqa: F401


logger = logging.getLogger(__name__)
