# apps/global_platform_settings/cache.py
"""
Redis cache accessor for the PlatformSettings singleton.

This module provides a single public function ``get_platform_settings()`` that
callers across the entire backend should use instead of querying the ORM
directly.  The caching strategy is:

  1. Try Redis (``PLATFORM_SETTINGS_CACHE_KEY``).
  2. On miss: read from PostgreSQL, populate cache with 60-second TTL.
  3. If both fail (offline/test): return an in-memory ``PlatformSettings``
     instance populated with safe production defaults.

The 60-second TTL is intentionally short because fee and rate changes made
through the Django Admin panel must propagate to all running processes quickly
to avoid charging the wrong commission on concurrent orders.

Usage::

    from apps.global_platform_settings.cache import get_platform_settings

    cfg = get_platform_settings()
    print(cfg.vendor_commission_rate)   # Decimal("0.10")
    print(cfg.measurement_fee_ngn)      # Decimal("1000.00")
"""

from __future__ import annotations

import logging
from decimal import Decimal

from django.core.cache import cache

logger = logging.getLogger("application")

# Imported lazily inside the function to prevent AppRegistryNotReady errors
# during early Django startup (e.g. settings import).
_CACHE_KEY = "fashionistar:global_platform_settings:v1"
_CACHE_TTL = 60  # seconds


def get_platform_settings():
    """Return the live PlatformSettings singleton, served from Redis when possible.

    Returns:
        PlatformSettings: The singleton instance (cached or freshly read from DB).
            Falls back to a default-populated in-memory instance if the database
            is unreachable (e.g. during CI tests without migrations).

    Raises:
        Never raises.  All exceptions are swallowed and a safe default is returned.
    """
    from apps.global_platform_settings.models import (  # local import — avoids circular
        PlatformSettings,
        SINGLETON_PK,
    )

    # 1. Cache hit
    cached = cache.get(_CACHE_KEY)
    if cached is not None:
        return cached

    # 2. Cache miss — read from database
    try:
        instance, _ = PlatformSettings.objects.get_or_create(pk=SINGLETON_PK)
        cache.set(_CACHE_KEY, instance, timeout=_CACHE_TTL)
        return instance
    except Exception as exc:
        # 3. Fallback — return a safe in-memory default so the platform never
        #    crashes due to a DB/Redis blip mid-request.
        logger.warning(
            "get_platform_settings: could not read from DB, using defaults. Reason: %s",
            exc,
        )
        instance = PlatformSettings(
            vendor_commission_rate=Decimal("0.1000"),
            client_platform_fee_rate=Decimal("0.0000"),
            measurement_fee_ngn=Decimal("1000.00"),
            advertisement_fee_ngn=Decimal("5000.00"),
            min_wallet_topup_ngn=Decimal("500.00"),
            max_wallet_topup_ngn=Decimal("5000000.00"),
            min_withdrawal_ngn=Decimal("1000.00"),
            max_withdrawal_ngn=Decimal("2000000.00"),
            max_daily_withdrawal_ngn=Decimal("5000000.00"),
            cod_enabled=True,
            in_store_payment_enabled=True,
            cod_confirmation_window_hours=72,
            cod_platform_commission_rate=Decimal("0.1000"),
            kyc_max_retry_attempts=3,
            kyc_lockout_hours=24,
            ngn_usd_rate=Decimal("0.00065000"),
            platform_name="Fashionistar",
            support_email="support@fashionistar.net",
            support_phone="+2349137654300",
        )
        return instance
