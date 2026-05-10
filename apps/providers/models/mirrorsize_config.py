"""
MirrorSizeProviderConfig — Admin-switchable MirrorSize / GetMeasured provider config.

Replaces hardcoded MIRRORSIZE_* Django settings entries with a DB-driven,
admin-editable singleton. Credentials stay in .env; this model manages
operational parameters and circuit state.
"""
from __future__ import annotations

from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.providers.models.base import AbstractProviderConfig


class MirrorSizeProviderConfig(AbstractProviderConfig):
    """
    Singleton controlling MirrorSize / GetMeasured widget integration.

    The `api_key` and `merchant_id` are sensitive credentials — they are read
    from Django settings (MIRRORSIZE_API_KEY, MIRRORSIZE_MERCHANT_ID) to keep
    secrets out of the database. This model tracks only operational parameters
    and the circuit breaker state.
    """

    product_name = models.CharField(
        max_length=120,
        default="GET_MEASURED",
        verbose_name=_("Product Name"),
        help_text=_(
            "MirrorSize product name used when generating access codes. "
            "Defaults to 'GET_MEASURED' (the measurement widget)."
        ),
    )
    browser_api_base_url = models.URLField(
        max_length=255,
        default="https://api.user.mirrorsize.com",
        verbose_name=_("Browser API Base URL"),
        help_text=_("Base URL for MirrorSize browser/widget API."),
    )
    user_home_base_url = models.URLField(
        max_length=255,
        default="https://user.mirrorsize.com/home",
        verbose_name=_("User Home Base URL"),
        help_text=_("Base URL for the MirrorSize user home (redirect target)."),
    )
    enabled = models.BooleanField(
        default=True,
        verbose_name=_("Enabled"),
        help_text=_(
            "Disable to deactivate MirrorSize widget integration across the platform."
        ),
    )
    access_code_ttl_seconds = models.PositiveIntegerField(
        default=3600,
        verbose_name=_("Access Code TTL (seconds)"),
        help_text=_("How long a generated MirrorSize access code remains valid."),
    )

    class Meta:
        app_label = "providers"
        verbose_name = _("MirrorSize Provider Configuration")
        verbose_name_plural = _("MirrorSize Provider Configuration")

    def __str__(self) -> str:
        status = "✅ Enabled" if self.enabled else "❌ Disabled"
        return f"MirrorSize Config [{status}] product={self.product_name}"
