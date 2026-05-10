# apps/global_platform_settings/signals.py
"""
Django signals for the GlobalPlatformSettings application.

Registered Handlers:
    post_migrate → ``seed_platform_settings``:
        Ensures the PlatformSettings singleton row (pk=1) exists after every
        migration run.  This is safe to run multiple times (idempotent via
        ``get_or_create``).

    post_save → ``bust_platform_settings_cache``:
        Invalidates the Redis cache key whenever the singleton is saved through
        the Django Admin, so updated fees propagate to all running processes
        within 60 seconds.
"""
from __future__ import annotations

import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

logger = logging.getLogger("application")


def seed_platform_settings(sender, **kwargs) -> None:
    """Idempotently create the PlatformSettings singleton row after migrations.

    Args:
        sender: The AppConfig that triggered the ``post_migrate`` signal.
        **kwargs: Additional signal keyword arguments (verbosity, interactive, etc.).
    """
    # Guard: only seed when this specific app's migrations complete
    if kwargs.get("app_config") and kwargs["app_config"].label != "global_platform_settings":
        return

    try:
        from apps.global_platform_settings.models import (  # noqa: PLC0415
            PlatformSettings,
            SINGLETON_PK,
        )

        obj, created = PlatformSettings.objects.get_or_create(pk=SINGLETON_PK)
        if created:
            logger.info("GlobalPlatformSettings: seeded default PlatformSettings singleton (pk=%s).", SINGLETON_PK)
        else:
            logger.debug("GlobalPlatformSettings: singleton already exists, skipping seed.")
    except Exception as exc:
        # Non-fatal — happens during the very first `migrate` before the table exists
        logger.debug("GlobalPlatformSettings: seed skipped (table not ready yet): %s", exc)


def bust_platform_settings_cache(sender, instance, **kwargs) -> None:
    """Bust the Redis cache whenever the PlatformSettings singleton is saved.

    Args:
        sender: The ``PlatformSettings`` model class.
        instance: The saved ``PlatformSettings`` instance.
        **kwargs: Additional signal keyword arguments (created, update_fields, etc.).
    """
    from django.core.cache import cache  # noqa: PLC0415

    from apps.global_platform_settings.models import PLATFORM_SETTINGS_CACHE_KEY  # noqa: PLC0415

    cache.delete(PLATFORM_SETTINGS_CACHE_KEY)
    logger.info("GlobalPlatformSettings: cache busted after admin save.")


def connect_signals() -> None:
    """Wire all signal handlers.  Called from ``GlobalPlatformSettingsConfig.ready()``."""
    from django.db.models.signals import post_migrate  # noqa: PLC0415

    from apps.global_platform_settings.models import PlatformSettings  # noqa: PLC0415

    post_migrate.connect(seed_platform_settings, dispatch_uid="global_platform_settings.seed")
    post_save.connect(
        bust_platform_settings_cache,
        sender=PlatformSettings,
        dispatch_uid="global_platform_settings.bust_cache",
    )


# Connect immediately on module import (apps.py ready() calls this module)
connect_signals()
