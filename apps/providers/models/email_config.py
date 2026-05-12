# apps/providers/models/email_config.py
"""
EmailProviderConfig — Admin-switchable email delivery provider singleton.

Replaces apps.admin_backend.models.EmailBackendConfig.
A backward-compat shim in admin_backend re-exports this model
so no existing callsites break.

Admin flow:
  1. Super admin logs in → Providers → Email Provider Configuration.
  2. Picks a backend from the dropdown (Brevo, Mailgun, Zoho, SMTP/Gmail, SendGrid).
  3. Saves → post_save signal busts provider cache → next email uses new backend.

No credentials are stored here — email backends source credentials from
Django settings (ANYMAIL dict keys / EMAIL_HOST_USER etc.) as per Anymail docs.
"""
from django.utils.translation import gettext_lazy as _

from apps.providers.models.base import AbstractProviderConfig
from apps.providers.fields import encrypt
from apps.providers.SMTP import EMAIL_BACKEND_CHOICES, get_email_backend_label
from django.db import models


class EmailProviderConfig(AbstractProviderConfig):
    """
    Singleton model controlling which email backend Django uses at runtime.

    The selected backend path is read by DatabaseConfiguredEmailBackend.__init__()
    on every cold-start (warm reads hit the Redis cache, never the DB).
    """

    email_backend = models.CharField(
        max_length=250,
        choices=EMAIL_BACKEND_CHOICES,
        default="django.core.mail.backends.smtp.EmailBackend",
        verbose_name=_("Active Email Backend"),
        help_text=_(
            "Choose the transactional email backend used by the platform. "
            "SMTP (Gmail) is acceptable for development or low-volume flows. "
            "Production environments should use Mailgun, SendGrid, Zoho "
            "ZeptoMail, or Brevo."
        ),
        db_index=True,
    )
    api_key = encrypt(
        models.CharField(
            max_length=512,
            blank=True,
            default="",
            verbose_name=_("API Key"),
            help_text=_("Optional provider API key stored encrypted for API-backed email providers."),
        )
    )
    api_secret = encrypt(
        models.CharField(
            max_length=512,
            blank=True,
            default="",
            verbose_name=_("API Secret"),
            help_text=_("Optional provider API secret stored encrypted when required."),
        )
    )
    sender_email = models.EmailField(
        blank=True,
        default="",
        verbose_name=_("Sender Email Override"),
        help_text=_("Optional from-address override for this provider."),
    )
    extra_config = encrypt(
        models.JSONField(
            default=dict,
            blank=True,
            verbose_name=_("Extra Configuration"),
            help_text=_("Provider-specific metadata such as region, domain, tags, or account IDs."),
        )
    )

    class Meta:
        app_label = "providers"
        verbose_name = _("Email Provider Configuration")
        verbose_name_plural = _("Email Provider Configuration")
        indexes = [
            models.Index(fields=["email_backend"], name="prov_email_backend_idx"),
        ]

    def __str__(self) -> str:
        return get_email_backend_label(self.email_backend)
