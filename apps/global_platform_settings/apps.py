# apps/global_platform_settings/apps.py
"""
AppConfig for the global_platform_settings Django application.

Registers the app under the label ``global_platform_settings`` and connects
the ``post_migrate`` signal that auto-seeds the singleton row on first deploy.
"""
from __future__ import annotations

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class GlobalPlatformSettingsConfig(AppConfig):
    """
    Django AppConfig for GlobalPlatformSettings.

    Attributes:
        name: Python module path to the application.
        label: Unique identifier used for database table prefixes.
        verbose_name: Human-readable name shown in Django Admin.
        default_auto_field: Primary key type for all models in this app.
    """

    name = "apps.global_platform_settings"
    label = "global_platform_settings"
    verbose_name = _("Global Platform Settings")
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self) -> None:
        """Import signal handlers when the application registry is ready."""
        import apps.global_platform_settings.signals  # noqa: F401  — registers post_migrate handler

        # Warm up the cache synchronously to avoid async context ORM operations at runtime
        try:
            from apps.global_platform_settings.cache import get_platform_settings
            get_platform_settings()
        except Exception:
            pass
