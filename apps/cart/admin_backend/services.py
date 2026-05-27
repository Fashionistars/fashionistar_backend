# apps/cart/admin_backend/services.py
from __future__ import annotations
import logging
from django.db import transaction
from apps.common.events import event_bus
from apps.cart.models.cart import Cart, CartActivityLog

logger = logging.getLogger(__name__)

@transaction.atomic
def admin_clear_cart(cart_id: str, admin_user) -> Cart:
    """
    Force clear a shopping cart by admin.
    """
    cart = Cart.objects.select_for_update().get(id=cart_id)
    cart.items.all().delete()
    
    CartActivityLog.objects.create(
        cart=cart,
        action="cart_cleared",
        metadata={"admin_cleared_by": admin_user.email},
    )
    
    logger.info("Admin %s cleared cart %s", admin_user.email, cart_id)
    event_bus.emit_on_commit(
        "admin.cart.cleared",
        cart_id=str(cart.id),
        admin_id=str(admin_user.id),
    )
    return cart
