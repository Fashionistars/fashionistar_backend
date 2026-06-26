# apps/providers/apps.py
"""
AppConfig for the Fashionistar Providers Registry Django application.

This application is the single authoritative registry for every third-party
integration the Fashionistar platform depends on.  It is organised into five
provider domains, each backed by an admin-managed DB config model that stores
credentials, selects the active driver, and controls sandbox vs live mode.

Provider Domains:
    Payment/    — Paystack, Flutterwave, OlivePay gateway drivers.
    KYC/        — Smile Identity, Dojah, Youverify identity verification.
    SMS/        — Termii, Twilio, BulkSMS Nigeria dispatch drivers.
    SMTP/       — Brevo, Mailgun, Zoho Mail transactional email drivers.
    Cloudinary/ — Cloudinary media upload & CDN delivery driver.


Each domain provides:
    - A ``ProviderConfig`` singleton DB model (admin-switchable, credential-storing).
    - A Redis cache-first config loader (TTL = 300 s for provider configs,
      60 s for payment gateway selection).
    - A ``CircuitBreaker`` decorator (5-failure threshold → OPEN → admin alert).
    - One or more driver classes implementing the domain abstract interface.

Registration:
    ``apps.providers`` is registered in ``INSTALLED_APPS`` in ``config/base.py``.
    Signal handlers are connected in ``ready()`` via ``apps.providers.signals``.

Migration Note:
    This app owns the ``ProviderConfig`` models in ``apps/providers/models/``.
    Admin backends previously in ``apps/admin_backend/`` have been fully
    consolidated here as of the Phase 9 provider registry finalisation.
"""
from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class ProvidersConfig(AppConfig):
    """
    Django AppConfig for the Fashionistar Providers Registry.

    Attributes:
        name: Python module path — ``"apps.providers"``.
        label: DB table prefix — ``"providers"``.
        verbose_name: Human-readable name shown in Django Admin.
        default_auto_field: BigAutoField for all provider models.
    """

    name = "apps.providers"
    label = "providers"
    verbose_name = _("Provider Registry")
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self) -> None:
        """Connect post_save signals for provider config cache invalidation.

        Called by Django once the application registry is fully populated.
        Importing ``signals`` here ensures the signal handlers are registered
        exactly once, regardless of how many times ``ready()`` is called.
        """
        # Register post_save signals for cache invalidation on provider config saves
        from apps.providers.signals import register_signals  # noqa: PLC0415

        register_signals()
