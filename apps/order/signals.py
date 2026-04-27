# apps/order/signals.py
import logging
from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.order.models import Order, OrderStatus

logger = logging.getLogger(__name__)


@receiver(post_save, sender=Order)
def on_order_created(sender, instance, created, **kwargs):
    if created:
        logger.info(
            "Order created: order_number=%s user=%s total=%s",
            instance.order_number,
            instance.user_id,
            instance.total_amount,
        )
