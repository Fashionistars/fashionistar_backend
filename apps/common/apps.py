"""
App configuration for the common app.

This module defines the configuration for the 'common' Django app,
which provides shared utilities, models, and permissions across the
project.

The ``ready()`` hook:
  1. Connects analytics signal handlers from ``apps.common.signals``
  2. Subscribes business-event handlers via the EventBus singleton.

Architecture — Event Bus vs Django Signals:
  ``signals.py`` handles ANALYTICS ONLY (post_save/post_delete counters).
  ``event_handlers.py`` handles BUSINESS LIFECYCLE EVENTS via the EventBus.
  No Django signals are used for cross-app business logic — ever.

NOTE: Async logging was moved to ``backend.apps.BackendConfig.ready()``
which runs first and configures all logging correctly across Django dev
server, Uvicorn, Daphne, and Celery.
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
        Wire signal receivers and EventBus subscriptions.
        Logging is configured by BackendConfig.ready() in backend/apps.py.
        """
        # 1. Analytics signal receivers (post_save / post_delete)
        import apps.common.signals  # noqa: F401

        # 2. EventBus subscriptions — business lifecycle events
        # Import here (not at module level) to avoid circular imports.
        from apps.common.events import event_bus
        from apps.common.event_handlers import on_user_registered
        event_bus.subscribe('user.registered', on_user_registered)


logger = logging.getLogger(__name__)
