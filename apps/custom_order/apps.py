# apps/custom_order/apps.py
from django.apps import AppConfig


class CustomOrderConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.custom_order"
    label = "custom_order"
    verbose_name = "Custom Orders (Bespoke Commissions)"
