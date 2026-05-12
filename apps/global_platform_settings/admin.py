# apps/global_platform_settings/admin.py
"""
Django Admin registration for the PlatformSettings singleton.

Design Decisions:
    - **Add blocked**: The ``has_add_permission`` guard prevents creating a
      second row once the singleton exists.
    - **Delete always blocked**: ``has_delete_permission`` returns ``False``
      unconditionally to protect the singleton invariant.
    - **Grouped fieldsets**: Non-technical admins can find and update settings
      without risk of accidentally touching unrelated fields.
    - **Post-save message**: A success banner confirms propagation delay
      (≤ 60 s) so admins know when changes will take effect.

Usage::

    Navigate to Django Admin → Global Platform Settings → Platform Settings
    and click the existing row to edit.  There is exactly one row.
"""
from __future__ import annotations

from django.contrib import admin, messages
from django.utils.translation import gettext_lazy as _

from apps.global_platform_settings.models import PlatformSettings


@admin.register(PlatformSettings)
class PlatformSettingsAdmin(admin.ModelAdmin):
    """
    Admin panel for the PlatformSettings singleton.

    Features:
        - List display shows the most operationally significant fields.
        - Fieldsets group related settings for clarity.
        - Add permission is denied when a row already exists.
        - Delete permission is unconditionally denied.
        - A success banner is shown after every save, reminding admins of the
          60-second propagation window.
    """

    list_display = [
        "vendor_commission_rate",
        "client_platform_fee_rate",
        "measurement_fee_ngn",
        "min_withdrawal_ngn",
        "cod_enabled",
        "in_store_payment_enabled",
        "updated_at",
    ]

    readonly_fields = ("updated_at",)

    fieldsets = (
        (_("💰 Commission & Platform Fees"), {
            "fields": (
                "vendor_commission_rate",
                "client_platform_fee_rate",
                "measurement_fee_ngn",
                "advertisement_fee_ngn",
            ),
            "description": _(
                "⚠️ Changes take effect within 60 seconds across all services. "
                "Commission rates are expressed as decimals: 0.10 = 10%."
            ),
        }),
        (_("💳 Wallet Limits"), {
            "fields": (
                "min_wallet_topup_ngn",
                "max_wallet_topup_ngn",
                "min_withdrawal_ngn",
                "max_withdrawal_ngn",
                "max_daily_withdrawal_ngn",
            ),
        }),
        (_("🏪 Cash / COD / In-store Payments"), {
            "fields": (
                "cod_enabled",
                "in_store_payment_enabled",
                "cod_platform_commission_rate",
                "cod_confirmation_window_hours",
            ),
            "description": _(
                "When COD or in-store payment is enabled, commission is still collected. "
                "Vendors must confirm delivery via the platform; bypassing triggers a dispute flag."
            ),
        }),
        (_("🪪 KYC Settings"), {
            "fields": (
                "kyc_max_retry_attempts",
                "kyc_lockout_hours",
            ),
        }),
        (_("💱 Exchange Rate"), {
            "fields": ("ngn_usd_rate",),
            "description": _("Fallback rate used when live rate lookup fails. Update regularly."),
        }),
        (_("🏢 Platform Identity"), {
            "fields": (
                "platform_name",
                "support_email",
                "support_phone",
                "terms_url",
                "privacy_url",
            ),
        }),
        (_("⏱ Timestamps"), {
            "fields": ("updated_at",),
            "classes": ("collapse",),
        }),
    )

    def has_add_permission(self, request) -> bool:
        """Block adding a second row — only one singleton is permitted.

        Args:
            request: The current HTTP request.

        Returns:
            bool: ``True`` only if no PlatformSettings row exists yet.
        """
        return not PlatformSettings.objects.exists()

    def has_delete_permission(self, request, obj=None) -> bool:
        """Unconditionally block deletion of the singleton.

        Args:
            request: The current HTTP request.
            obj: The object being acted upon (ignored).

        Returns:
            bool: Always ``False``.
        """
        return False

    def save_model(self, request, obj, form, change) -> None:
        """Save the singleton and display a propagation-time banner.

        Args:
            request: The current HTTP request.
            obj: The ``PlatformSettings`` instance being saved.
            form: The bound ``ModelForm`` submitted from the admin.
            change: ``True`` if this is an edit, ``False`` if a new object.
        """
        super().save_model(request, obj, form, change)
        messages.success(
            request,
            _(
                "✅ Platform settings saved. "
                "New values will be live across all services within 60 seconds."
            ),
        )
