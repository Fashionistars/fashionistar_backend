# apps/cart/apps.py
from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class CartConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.cart"
    verbose_name = _("Shopping Cart")

    def ready(self):
        try:
            import apps.cart.signals  # noqa: F401
        except ImportError:
            pass

        try:
            from auditlog.registry import auditlog
            from apps.cart.models import Cart, CartItem
            auditlog.register(Cart)
            auditlog.register(CartItem)
        except Exception:
            import logging
            logging.getLogger("application").debug("auditlog cart registration skipped")
