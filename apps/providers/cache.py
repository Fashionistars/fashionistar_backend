# apps/providers/cache.py
"""
Provider configuration cache layer.

All provider configs are served from Redis with a 5-minute TTL.
On any admin save, the post_save signal calls invalidate_provider_cache()
to ensure zero-delay propagation of provider switches.

Cache key format: ``provider_cfg:<app_label>:<model_name>``
  Examples:
    - provider_cfg:providers:emailproviderconfig   → EmailProviderConfig singleton
    - provider_cfg:providers:smsproviderconfig     → SMSProviderConfig singleton
    - provider_cfg:providers:kycproviderconfig     → KYCProviderConfig singleton
    - provider_cfg:providers:cloudinaryproviderconfig → CloudinaryProviderConfig
    - provider_cfg:providers:mirrorsizeproviderconfig → MirrorSizeProviderConfig

Thread-safety: Django cache.get/set operations are atomic at the Redis level.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from django.core.cache import cache

if TYPE_CHECKING:
    from apps.providers.models import (
        CloudinaryProviderConfig,
        EmailProviderConfig,
        KYCProviderConfig,
        MirrorSizeProviderConfig,
        SMSProviderConfig,
    )

logger = logging.getLogger("application")

PROVIDER_CACHE_TTL = 300  # 5 minutes — balances freshness with DB load


# ── Cache Key Helpers ─────────────────────────────────────────────────────────


def _cache_key(model_class) -> str:
    """Derive a deterministic cache key from the model class."""
    meta = model_class._meta
    return f"provider_cfg:{meta.app_label}:{meta.model_name}"


# ── Generic Loader ────────────────────────────────────────────────────────────


def _get_or_load(model_class):
    """
    Cache-first read pattern for any singleton provider config model.

    Miss path:
      1. Query DB for the single config row.
      2. If none exists, log a warning and return an empty (unsaved) instance.
      3. Cache the result for PROVIDER_CACHE_TTL seconds.
    """
    key = _cache_key(model_class)
    cached = cache.get(key)
    if cached is not None:
        return cached

    instance = model_class.objects.first()
    if instance is None:
        logger.warning(
            "No %s row found in database. "
            "Using unconfigured default — run migrations and create a config record via Django Admin.",
            model_class.__name__,
        )
        instance = model_class()  # empty instance (not saved)

    cache.set(key, instance, PROVIDER_CACHE_TTL)
    logger.debug("Provider cache MISS → loaded %s from DB", model_class.__name__)
    return instance


# ── Public Accessors ──────────────────────────────────────────────────────────


def get_email_provider_config() -> "EmailProviderConfig":
    """Return the active EmailProviderConfig (Redis → DB → default)."""
    from apps.providers.models import EmailProviderConfig

    return _get_or_load(EmailProviderConfig)


def get_sms_provider_config() -> "SMSProviderConfig":
    """Return the active SMSProviderConfig (Redis → DB → default)."""
    from apps.providers.models import SMSProviderConfig

    return _get_or_load(SMSProviderConfig)


def get_kyc_provider_config() -> "KYCProviderConfig":
    """Return the active KYCProviderConfig (Redis → DB → default)."""
    from apps.providers.models import KYCProviderConfig

    return _get_or_load(KYCProviderConfig)


def get_cloudinary_provider_config() -> "CloudinaryProviderConfig":
    """Return the active CloudinaryProviderConfig (Redis → DB → default)."""
    from apps.providers.models import CloudinaryProviderConfig

    return _get_or_load(CloudinaryProviderConfig)


def get_mirrorsize_provider_config() -> "MirrorSizeProviderConfig":
    """Return the active MirrorSizeProviderConfig (Redis → DB → default)."""
    from apps.providers.models import MirrorSizeProviderConfig

    return _get_or_load(MirrorSizeProviderConfig)


# ── Cache Invalidation ────────────────────────────────────────────────────────


def invalidate_provider_cache(model_class) -> None:
    """
    Bust the provider config cache for the given model class.

    Called from:
      - AbstractProviderConfig.save() (always, on every admin edit)
      - post_save signal in apps.providers.signals

    This guarantees the NEXT request loads the freshest config from DB.
    """
    key = _cache_key(model_class)
    cache.delete(key)
    logger.info(
        "Provider cache busted for %s (key=%s). Next request will reload from DB.",
        model_class.__name__,
        key,
    )


__all__ = [
    "PROVIDER_CACHE_TTL",
    "get_cloudinary_provider_config",
    "get_email_provider_config",
    "get_kyc_provider_config",
    "get_mirrorsize_provider_config",
    "get_sms_provider_config",
    "invalidate_provider_cache",
]
