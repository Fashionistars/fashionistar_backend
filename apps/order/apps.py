# apps/order/apps.py
from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class OrderConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.order"
    verbose_name = _("Orders")

    def ready(self):
        try:
            from auditlog.registry import auditlog
            from apps.order.models import Order, CartOrderItem, OrderStatusHistory
            auditlog.register(Order)
            auditlog.register(CartOrderItem)
            auditlog.register(OrderStatusHistory)
        except Exception:
            import logging
            logging.getLogger("application").debug("auditlog order registration skipped")
