# apps/kyc/apps.py
"""
KYC Domain AppConfig — SCAFFOLD ONLY (not yet in INSTALLED_APPS).

Add "apps.kyc" to INSTALLED_APPS when the KYC sprint begins.
"""
from django.apps import AppConfig


class KycConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.kyc"
    verbose_name = "KYC Compliance"
    label = "kyc"

    def ready(self) -> None:
        # Wire signal listeners / event bus subscriptions here when implemented
        pass
