# apps/providers/signals.py
"""
Signal handlers for the providers registry.

Responsibilities:
  1. Cache invalidation on any provider config save.
  2. post_migrate: ensure a default singleton row exists for every provider
     config model so the platform works immediately after `manage.py migrate`.

Registered in ProvidersConfig.ready() (apps/providers/apps.py).
"""
from __future__ import annotations

import logging

from django.apps import apps
from django.db.models.signals import post_migrate, post_save
from django.dispatch import receiver

logger = logging.getLogger("application")


# ── Cache Invalidation ────────────────────────────────────────────────────────


def _invalidate_on_save(sender, instance, **kwargs) -> None:
    """Generic cache invalidation handler for any provider config model."""
    try:
        from apps.providers.cache import invalidate_provider_cache
        invalidate_provider_cache(sender)
    except Exception as exc:
        logger.error(
            "Provider cache invalidation signal failed for %s: %s",
            sender.__name__, exc,
        )


def register_signals() -> None:
    """
    Register post_save signals for all provider config models.
    Called from ProvidersConfig.ready() to avoid AppRegistryNotReady errors.
    """
    from apps.providers.models import (
        CloudinaryProviderConfig,
        EmailProviderConfig,
        KYCProviderConfig,
        MirrorSizeProviderConfig,
        SMSProviderConfig,
    )

    for model in (
        EmailProviderConfig,
        SMSProviderConfig,
        KYCProviderConfig,
        CloudinaryProviderConfig,
        MirrorSizeProviderConfig,
    ):
        post_save.connect(_invalidate_on_save, sender=model, weak=False)
        logger.debug("Provider post_save signal registered for %s", model.__name__)


# ── post_migrate: Default Singleton Creation ──────────────────────────────────

_PROVIDER_MODELS = [
    ("providers", "EmailProviderConfig"),
    ("providers", "SMSProviderConfig"),
    ("providers", "KYCProviderConfig"),
    ("providers", "CloudinaryProviderConfig"),
    ("providers", "MirrorSizeProviderConfig"),
]


@receiver(post_migrate)
def create_default_provider_configs(sender, **kwargs) -> None:
    """
    Ensure every provider config has a default singleton row after migration.

    This handler fires after every migrate / post_migrate event but only
    creates rows if they do not already exist, so it is completely idempotent.

    Triggers on the 'providers' app migration only to avoid running 5× per
    migrate command.
    """
    if sender.name != "apps.providers":
        return

    for app_label, model_name in _PROVIDER_MODELS:
        try:
            Model = apps.get_model(app_label, model_name)
            if not Model.objects.exists():
                Model.objects.create()
                logger.info(
                    "post_migrate: Created default %s singleton.", model_name
                )
            else:
                logger.debug(
                    "post_migrate: %s singleton already exists — skipping.", model_name
                )
        except Exception as exc:
            logger.error(
                "post_migrate: Failed to create default %s — %s", model_name, exc, exc_info=True
            )
