# apps/cart/signals.py
import logging
from django.db.models.signals import post_save
from django.dispatch import receiver
from apps.cart.models import Cart

logger = logging.getLogger(__name__)

@receiver(post_save, sender=Cart)
def on_cart_save(sender, instance, created, **kwargs):
    if created:
        logger.debug("Cart created for user=%s", instance.user_id)
