# apps/providers/admin.py
"""
Django Admin registrations for the Provider Registry.

All provider config models use a unified admin pattern:
  - No add permission if a row already exists (singleton enforcement in UI)
  - No delete permission (deletion blocked at model level too)
  - Health status + circuit state displayed as read-only diagnostics
  - Timestamps collapsed into a sidebar section
"""

from __future__ import annotations

from django.contrib import admin, messages
from django.utils.translation import gettext_lazy as _

from apps.providers.models import (
    CloudinaryProviderConfig,
    EmailProviderConfig,
    KYCProviderConfig,
    MirrorSizeProviderConfig,
    SMSProviderConfig,
)

# ── Shared Admin Base ─────────────────────────────────────────────────────────


class ProviderConfigAdminBase(admin.ModelAdmin):
    """
    Base admin mixin for singleton provider config models.

    Enforces:
      - Singleton: add blocked if a row exists.
      - No delete from UI.
      - Health and circuit state read-only.
    """

    readonly_fields = (
        "health_status",
        "last_health_check",
        "circuit_state",
        "failure_count",
        "last_failure_at",
        "created_at",
        "updated_at",
    )

    def has_add_permission(self, request) -> bool:
        return not self.model.objects.exists()

    def has_delete_permission(self, request, obj=None) -> bool:
        return False

    def save_model(self, request, obj, form, change) -> None:
        super().save_model(request, obj, form, change)
        messages.success(
            request,
            _(
                "%(model)s saved — provider cache has been cleared. "
                "The new configuration is now active."
            )
            % {"model": self.model.__name__},
        )


# ── Email Provider Admin ──────────────────────────────────────────────────────


@admin.register(EmailProviderConfig)
class EmailProviderConfigAdmin(ProviderConfigAdminBase):
    list_display = ["email_backend", "health_status", "circuit_state", "updated_at"]
    fieldsets = (
        (
            _("Email Backend"),
            {
                "fields": (
                    "email_backend",
                    "sender_email",
                    "api_key",
                    "api_secret",
                    "extra_config",
                ),
                "description": _(
                    "Choose the active transactional email backend. "
                    "Credentials saved here are encrypted and let admins rotate "
                    "provider details without redeploying."
                ),
            },
        ),
        (
            _("Circuit Breaker & Health"),
            {
                "fields": (
                    "health_status",
                    "last_health_check",
                    "circuit_state",
                    "failure_count",
                    "last_failure_at",
                ),
                "classes": ("collapse",),
            },
        ),
        (
            _("Timestamps"),
            {
                "fields": ("created_at", "updated_at"),
                "classes": ("collapse",),
            },
        ),
    )


# ── SMS Provider Admin ────────────────────────────────────────────────────────


@admin.register(SMSProviderConfig)
class SMSProviderConfigAdmin(ProviderConfigAdminBase):
    list_display = ["sms_backend", "health_status", "circuit_state", "updated_at"]
    fieldsets = (
        (
            _("SMS Provider"),
            {
                "fields": (
                    "sms_backend",
                    "sender_id",
                    "api_key",
                    "api_secret",
                    "extra_config",
                ),
                "description": _(
                    "Choose the active SMS provider class. "
                    "Credentials saved here are encrypted and are used before "
                    "environment fallback values."
                ),
            },
        ),
        (
            _("Circuit Breaker & Health"),
            {
                "fields": (
                    "health_status",
                    "last_health_check",
                    "circuit_state",
                    "failure_count",
                    "last_failure_at",
                ),
                "classes": ("collapse",),
            },
        ),
        (
            _("Timestamps"),
            {
                "fields": ("created_at", "updated_at"),
                "classes": ("collapse",),
            },
        ),
    )


# ── KYC Provider Admin ────────────────────────────────────────────────────────


@admin.register(KYCProviderConfig)
class KYCProviderConfigAdmin(ProviderConfigAdminBase):
    list_display = [
        "provider_slug",
        "sandbox_mode",
        "health_status",
        "circuit_state",
        "failure_count",
        "updated_at",
    ]
    fieldsets = (
        (
            _("Provider Selection"),
            {
                "fields": ("provider_slug", "sandbox_mode"),
                "description": _(
                    "⚠️ IMPORTANT: Set sandbox_mode=True while testing with sandbox credentials. "
                    "Switch to sandbox_mode=False ONLY after live credentials are fully verified."
                ),
            },
        ),
        (
            _("Credentials (Encrypted at Rest)"),
            {
                "fields": ("api_key", "api_secret", "webhook_secret", "extra_config"),
                "description": _(
                    "Credentials are stored encrypted in the database. "
                    "Never share these values. Rotate credentials via the provider dashboard."
                ),
            },
        ),
        (
            _("Endpoint Configuration"),
            {
                "fields": ("base_url", "webhook_idempotency_ttl_seconds"),
                "description": _(
                    "Leave base_url blank to use the provider's default URL. "
                    "Set to the sandbox URL when sandbox_mode=True."
                ),
                "classes": ("collapse",),
            },
        ),
        (
            _("Circuit Breaker & Health"),
            {
                "fields": (
                    "health_status",
                    "last_health_check",
                    "circuit_state",
                    "failure_count",
                    "last_failure_at",
                ),
                "classes": ("collapse",),
            },
        ),
        (
            _("Timestamps"),
            {
                "fields": ("created_at", "updated_at"),
                "classes": ("collapse",),
            },
        ),
    )

    def get_readonly_fields(self, request, obj=None):
        """Show provider_slug as readonly once configured to prevent accidental switches."""
        base = list(super().get_readonly_fields(request, obj))
        if obj and obj.provider_slug:  # if object exists and has slug → lock it
            base.append("provider_slug")
        return base


# ── Cloudinary Provider Admin ─────────────────────────────────────────────────


@admin.register(CloudinaryProviderConfig)
class CloudinaryProviderConfigAdmin(ProviderConfigAdminBase):
    list_display = [
        "upload_preset_images",
        "enabled",
        "health_status",
        "circuit_state",
        "updated_at",
    ]
    fieldsets = (
        (
            _("Upload Settings"),
            {
                "fields": (
                    "enabled",
                    "upload_preset_images",
                    "upload_preset_videos",
                    "signature_ttl_seconds",
                    "max_image_bytes",
                    "max_video_bytes",
                ),
                "description": _(
                    "Cloudinary credentials (CLOUDINARY_CLOUD_NAME, API_KEY, API_SECRET) "
                    "are configured via environment variables, not here."
                ),
            },
        ),
        (
            _("Circuit Breaker & Health"),
            {
                "fields": (
                    "health_status",
                    "last_health_check",
                    "circuit_state",
                    "failure_count",
                    "last_failure_at",
                ),
                "classes": ("collapse",),
            },
        ),
        (
            _("Timestamps"),
            {
                "fields": ("created_at", "updated_at"),
                "classes": ("collapse",),
            },
        ),
    )


# ── MirrorSize Provider Admin ─────────────────────────────────────────────────


@admin.register(MirrorSizeProviderConfig)
class MirrorSizeProviderConfigAdmin(ProviderConfigAdminBase):
    list_display = [
        "product_name",
        "enabled",
        "health_status",
        "circuit_state",
        "updated_at",
    ]
    fieldsets = (
        (
            _("Widget Settings"),
            {
                "fields": (
                    "enabled",
                    "product_name",
                    "browser_api_base_url",
                    "user_home_base_url",
                    "access_code_ttl_seconds",
                ),
                "description": _(
                    "MirrorSize credentials (MIRRORSIZE_API_KEY, MIRRORSIZE_MERCHANT_ID) "
                    "are configured via environment variables, not stored here."
                ),
            },
        ),
        (
            _("Circuit Breaker & Health"),
            {
                "fields": (
                    "health_status",
                    "last_health_check",
                    "circuit_state",
                    "failure_count",
                    "last_failure_at",
                ),
                "classes": ("collapse",),
            },
        ),
        (
            _("Timestamps"),
            {
                "fields": ("created_at", "updated_at"),
                "classes": ("collapse",),
            },
        ),
    )
