# apps/providers/models/sms_config.py
"""
SMSProviderConfig — Admin-switchable SMS delivery provider singleton.

Replaces apps.admin_backend.models.SMSBackendConfig.
A backward-compat shim in admin_backend re-exports this model
so no existing callsites break.

Admin flow:
  1. Super admin logs in → Providers → SMS Provider Configuration.
  2. Picks from Twilio / Termii / BulkSMS NG.
  3. Saves → cache bust → next SMS dispatch uses the new provider.

Security note:
  - API credentials (TWILIO_ACCOUNT_SID, TERMII_API_KEY etc.) remain
    in Django settings / .env files. This model only stores the provider
    class path (safe to store in DB).
"""

from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.providers.models.base import AbstractProviderConfig
from apps.providers.fields import encrypt
from apps.providers.SMS import SMS_BACKEND_CHOICES, get_sms_provider_label


class SMSProviderConfig(AbstractProviderConfig):
    """
    Singleton model controlling which SMS provider class is instantiated at runtime.

    The selected provider path is read by DatabaseConfiguredSMSBackend.__init__()
    on every cold-start (warm reads hit the Redis cache).
    """

    sms_backend = models.CharField(
        max_length=250,
        choices=SMS_BACKEND_CHOICES,
        default="apps.providers.SMS.twilio.TwilioSMSProvider",
        verbose_name=_("Active SMS Provider"),
        help_text=_(
            "Choose the active SMS provider class for the system. "
            "NOTE: Ensure the corresponding API credentials (Keys/Secrets) are "
            "correctly set in your Server Environment Variables before switching."
        ),
        db_index=True,
    )
    api_key = encrypt(
        models.CharField(
            max_length=512,
            blank=True,
            default="",
            verbose_name=_("API Key / Token"),
            help_text=_("Encrypted SMS provider API key/token. Used before environment fallback."),
        )
    )
    api_secret = encrypt(
        models.CharField(
            max_length=512,
            blank=True,
            default="",
            verbose_name=_("API Secret"),
            help_text=_("Encrypted SMS provider API secret when the selected provider requires one."),
        )
    )
    sender_id = models.CharField(
        max_length=80,
        blank=True,
        default="",
        verbose_name=_("Sender ID / From Number"),
        help_text=_("Provider sender ID, short code, or phone number override."),
    )
    extra_config = encrypt(
        models.JSONField(
            default=dict,
            blank=True,
            verbose_name=_("Extra Configuration"),
            help_text=_("Provider-specific metadata such as route, channel, region, or DND policy."),
        )
    )

    class Meta:
        app_label = "providers"
        verbose_name = _("SMS Provider Configuration")
        verbose_name_plural = _("SMS Provider Configuration")
        indexes = [
            models.Index(fields=["sms_backend"], name="prov_sms_backend_idx"),
        ]

    def __str__(self) -> str:
        return get_sms_provider_label(self.sms_backend)
