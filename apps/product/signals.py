# apps/product/signals.py
"""
Post-save signals for the Product domain.

Responsibilities:
  - Update ModelAnalytics counters on product create/update.
  - Invalidate related caches on product status changes.
"""

import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.product.models import Product

logger = logging.getLogger(__name__)


@receiver(post_save, sender=Product)
def update_product_analytics(sender, instance, created, **kwargs):
    """Update ModelAnalytics on product creation."""
    try:
        from apps.common.models import ModelAnalytics
        if created:
            ModelAnalytics.record_created(
                model_name="Product",
                app_label="product",
            )
        else:
            ModelAnalytics._dispatch(
                model_name="Product",
                app_label="product",
                total_updated=1,
            )
    except Exception:
        pass  # Never block on analytics
