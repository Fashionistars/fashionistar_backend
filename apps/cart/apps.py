# apps/cart/apps.py
"""AppConfig for the Shopping Cart domain."""
from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class CartConfig(AppConfig):
    """AppConfig for the Cart & Checkout domain."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.cart"
    verbose_name = _("Shopping Cart")

    def ready(self) -> None:
        """Register Cart models with django-auditlog on app startup."""
        try:
            from auditlog.registry import auditlog
            from apps.cart.models import Cart, CartItem

            auditlog.register(Cart)
            auditlog.register(CartItem)
        except Exception:
            import logging
            logging.getLogger("application").debug("auditlog cart registration skipped")
