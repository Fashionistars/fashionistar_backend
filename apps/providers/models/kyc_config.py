# apps/providers/models/kyc_config.py
"""
KYCProviderConfig — Admin-switchable KYC identity verification provider singleton.

Supported providers:
  - Smile Identity  (West/East Africa BVN/NIN + biometric liveness)
  - Dojah           (Nigeria-native BVN/NIN lookup + face match)
  - Youverify       (Identity verification + document check)

Admin flow:
  1. Super admin logs in → Providers → KYC Provider Configuration.
  2. Selects provider, enters sandbox API key, sets sandbox_mode=True for testing.
  3. Saves → post_save signal busts cache → next KYC dispatch uses new credentials.
  4. After testing: toggles sandbox_mode=False and swaps to live keys.

Security contract:
  - api_key, api_secret, webhook_secret are stored encrypted at rest
    using django-cryptography EncryptedCharField.
  - extra_config (JSON) is also encrypted to protect partner_id / auth tokens.
  - The circuit breaker tracks per-provider failure rate. On 3 consecutive
    failures the circuit OPENS and the first superuser receives an alert email.

CBN / NDPR compliance note:
  - No raw BVN/NIN numbers may be stored here or anywhere in the application.
  - The KycService layer stores only salted SHA-256 hashes + last-four markers.
  - provider_reference (external job/session ID) is the only cross-reference kept.
"""
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.providers.fields import encrypt
from apps.providers.models.base import AbstractProviderConfig
from apps.providers.KYC import KYC_PROVIDER_CHOICES, get_kyc_provider_label, get_kyc_provider_class_path


class KYCProviderConfig(AbstractProviderConfig):
    """
    Singleton model controlling which KYC verification provider is used at runtime.

    Credentials are per-provider. The `extra_config` JSONField accommodates
    provider-specific extras (e.g. Smile ID partner_id, Youverify account_id).

    One and only one row may exist (singleton enforcement from AbstractProviderConfig).
    """

    # ── Provider Selection ────────────────────────────────────────────────────
    provider_slug = models.CharField(
        max_length=30,
        choices=KYC_PROVIDER_CHOICES,
        default="dojah",
        verbose_name=_("KYC Provider"),
        help_text=_(
            "Select the active KYC identity verification provider. "
            "Switch here when rotating providers without redeploying."
        ),
        db_index=True,
    )

    # ── Credentials (stored encrypted at rest) ────────────────────────────────
    api_key = encrypt(
        models.CharField(
            max_length=512,
            blank=True,
            default="",
            verbose_name=_("API Key / App ID"),
            help_text=_("Primary API key or Application ID for the selected provider."),
        )
    )

    api_secret = encrypt(
        models.CharField(
            max_length=512,
            blank=True,
            default="",
            verbose_name=_("API Secret / Private Key"),
            help_text=_("API secret or private key. Leave blank if not required by the provider."),
        )
    )

    webhook_secret = encrypt(
        models.CharField(
            max_length=512,
            blank=True,
            default="",
            verbose_name=_("Webhook Secret"),
            help_text=_(
                "HMAC signing secret for validating inbound KYC provider webhook callbacks. "
                "Required for idempotent webhook processing."
            ),
        )
    )

    extra_config = encrypt(
        models.JSONField(
            default=dict,
            blank=True,
            verbose_name=_("Extra Configuration"),
            help_text=_(
                "Provider-specific JSON extras. "
                "Examples: {'partner_id': 'xxx'} for Smile ID, "
                "{'account_id': 'yyy'} for Youverify."
            ),
        )
    )

    # ── Endpoint Configuration ────────────────────────────────────────────────
    base_url = models.URLField(
        max_length=500,
        blank=True,
        default="",
        verbose_name=_("API Base URL Override"),
        help_text=_(
            "Leave blank to use the provider's default production URL. "
            "Set to the sandbox URL when sandbox_mode=True."
        ),
    )

    sandbox_mode = models.BooleanField(
        default=True,
        verbose_name=_("Sandbox / Test Mode"),
        help_text=_(
            "When enabled, all KYC requests are routed to the provider sandbox. "
            "Disable only after live credentials have been validated end-to-end."
        ),
    )

    # ── Idempotency Window ────────────────────────────────────────────────────
    webhook_idempotency_ttl_seconds = models.PositiveIntegerField(
        default=86400,  # 24 hours
        verbose_name=_("Webhook Idempotency TTL (seconds)"),
        help_text=_(
            "Time window for deduplicating repeated webhook deliveries "
            "for the same provider_reference. Default: 86400 (24 hours)."
        ),
    )

    class Meta:
        app_label = "providers"
        verbose_name = _("KYC Provider Configuration")
        verbose_name_plural = _("KYC Provider Configuration")
        indexes = [
            models.Index(fields=["provider_slug"], name="prov_kyc_slug_idx"),
        ]

    def __str__(self) -> str:
        mode_tag = "🧪 SANDBOX" if self.sandbox_mode else "🟢 LIVE"
        return f"{get_kyc_provider_label(self.provider_slug)} [{mode_tag}]"

    def get_provider_class_path(self) -> str:
        """Return the Python import path for the currently selected provider driver."""
        return get_kyc_provider_class_path(self.provider_slug)
