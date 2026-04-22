# apps/vendor/apps.py
"""
Vendor domain AppConfig.

The vendor domain intentionally DOES NOT auto-provision a profile on
registration. A vendor profile is created only from the explicit
``/api/v1/vendor/setup/`` workflow after the user reaches the setup gate.
"""
from django.apps import AppConfig


class VendorConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.vendor"
    verbose_name = "Vendor Domain"
    label = "vendor_domain"

    def ready(self) -> None:
        from apps.vendor.events import register_listeners  # noqa: F401
        register_listeners()
