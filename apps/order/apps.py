# apps/order/apps.py
from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class OrderConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.order"
    verbose_name = _("Orders")

    def ready(self):
        try:
            import apps.order.signals  # noqa: F401
        except ImportError:
            pass

        try:
            from auditlog.registry import auditlog
            from apps.order.models import Order, OrderItem, OrderStatusHistory
            auditlog.register(Order)
            auditlog.register(OrderItem)
            auditlog.register(OrderStatusHistory)
        except Exception:
            import logging
            logging.getLogger("application").debug("auditlog order registration skipped")
