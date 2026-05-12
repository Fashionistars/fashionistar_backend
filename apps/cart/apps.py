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
            # WE REALLY NEED TO CORRECT THE IMPORTION PATH OF ALL OUR AUDIT LOGS MODELS TO PROFESSSIONALLY MAKE USE OF OUR CUSTOMIZED APPS/AUDIT_LOG/SERVICES  FOR THE CART_AUDITLOGS SERVICES SPECIFICALLY WIRED FOR THE CART ITEMS, AND REMEMBER TO DELETE THE APPS/CART/SIGNALS BECAUSE WE AGREED ON NOT MAKING USE OF SIGNAL, INSTEAD MAKE USE OF OUR CUSTOMIZED APPS/COMMON/EVENTS.PY TO WIRE AND SPIN UP AND EVENT USING TRANSACTION.ON_COMMIT PLEASE,   ALSO MAKE SURE THAT WE EXCALATE, UPGRADE, UPDATE, EXPAND AND PROFESSIOINALLY ENLOARGE ALL  OUR CUSTOM AUDIT LOG FILES, FOLDERS, MODULES, FUNCTIONS, CLASSES AND THE REST OF IT TO PROFEESIONALLY ACCOMMODATE EACH AND EVERY SECTIONS, LAYER, APPS, PATTERN AND ALL OUR INDUSTRIALLY ENTERPRISE PRODUCTIONS GRADE APPS, AND SERVICES WHTI SELECTOR AND FUNCTIONS AND OTHER CLASSES AND OTHER MODULES AND ALL OTHER PARTS OF OUR ENTIRE BACKEND PROJECT FOLDERS PLEASE
            from auditlog.registry import auditlog
            from apps.cart.models import Cart, CartItem

            auditlog.register(Cart)
            auditlog.register(CartItem)
        except Exception:
            import logging

            logging.getLogger("application").debug("auditlog cart registration skipped")
