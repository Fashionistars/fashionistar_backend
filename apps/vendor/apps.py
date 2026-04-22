# apps/vendor/apps.py
"""
Vendor domain AppConfig.

Wires EventBus listeners for:
  - user.registered (role=vendor) → provision VendorProfile + setup state
  - user.verified                 → unlock vendor onboarding flow
"""
from django.apps import AppConfig


class VendorConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.vendor"
    verbose_name = "Vendor Domain"
    label = "vendor"

    def ready(self) -> None:
        from apps.vendor.events import register_listeners  # noqa: F401
        register_listeners()
