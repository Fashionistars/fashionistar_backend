# apps/payment/signals.py
"""
Payment app Django signals.

Signals registered here:
  - post_save on PaymentProvider  → bust active gateway cache in Redis
"""
from __future__ import annotations

import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

logger = logging.getLogger("application")


@receiver(post_save)
def bust_payment_gateway_cache(sender, **kwargs) -> None:
    """
    Bust the active payment gateway code cache whenever a PaymentProvider row is saved.

    This ensures that switching the active gateway in the Django admin takes effect
    within seconds (next request resolves from DB, then re-caches for 5 min).

    Lazy import to prevent circular import during app initialization.
    """
    # Use string comparison to avoid circular import at module load time
    if sender.__name__ != "PaymentProvider":
        return

    try:
        from apps.payment.orchestrator import bust_gateway_cache
        bust_gateway_cache()
        logger.info(
            "payment.signals: PaymentProvider saved — active gateway cache busted."
        )
    except Exception as exc:
        logger.warning(
            "payment.signals: Failed to bust gateway cache after PaymentProvider save: %s",
            exc,
        )
