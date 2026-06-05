# apps/notification/models/push_device.py
"""
PushDevice — FCM / APNs device token registry for push notifications.

Architecture:
  - One row per device per user. A user can have multiple devices.
  - Tokens are invalidated and removed when a device is unregistered
    (on FCM/APNs delivery error, or explicit logout).
  - device_id is a client-side fingerprint (UUID from app) used to detect
    duplicate registrations — always upsert on token refresh.
  - Platform distinguishes FCM (android + web) from APNs (iOS).

GDPR:
  - Tokens are ephemeral and PII-linked. Deleted on user account deletion.
  - `last_used_at` timestamps are used for automated token pruning after
    90 days of inactivity (GDPR data minimization principle).
"""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.common.models import TimeStampedModel


class PushDevice(TimeStampedModel):
    """
    Push notification device token for FCM (Android/Web) or APNs (iOS).

    Attributes:
        user: Owning user. Cascade-deleted with account.
        platform: 'fcm' (Android/Web) or 'apns' (iOS).
        device_id: Client-generated UUID for idempotent upsert.
        token: FCM registration token or APNs device token.
        device_name: Human-readable label (e.g. "My iPhone 15").
        app_version: App version string for diagnostics.
        os_version: OS version string for diagnostics.
        is_active: False = token invalidated / device unregistered.
        last_used_at: Updated on each successful push delivery.
    """

    class Platform(models.TextChoices):
        FCM = "fcm", _("Firebase Cloud Messaging (Android/Web)")
        APNS = "apns", _("Apple Push Notification Service (iOS)")
        WEB = "web", _("Web Push (VAPID)")

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="push_devices",
        verbose_name=_("User"),
    )
    platform = models.CharField(
        max_length=5,
        choices=Platform.choices,
        db_index=True,
        verbose_name=_("Platform"),
    )
    device_id = models.CharField(
        max_length=128,
        db_index=True,
        verbose_name=_("Device ID"),
        help_text=_("Client-generated UUID. Used for idempotent token upsert."),
    )
    token = models.TextField(
        verbose_name=_("Push Token"),
        help_text=_("FCM registration token or APNs device token."),
    )
    device_name = models.CharField(
        max_length=200,
        blank=True,
        verbose_name=_("Device Name"),
        help_text=_('Human-readable label, e.g. "My iPhone 15".'),
    )
    app_version = models.CharField(
        max_length=30,
        blank=True,
        verbose_name=_("App Version"),
    )
    os_version = models.CharField(
        max_length=30,
        blank=True,
        verbose_name=_("OS Version"),
    )
    is_active = models.BooleanField(
        default=True,
        db_index=True,
        verbose_name=_("Active"),
        help_text=_("False = token invalidated. Pruned by cleanup task."),
    )
    last_used_at = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
        verbose_name=_("Last Used At"),
    )

    class Meta:
        verbose_name = _("Push Device")
        verbose_name_plural = _("Push Devices")
        ordering = ["-created_at"]
        unique_together = [("user", "device_id")]
        indexes = [
            models.Index(fields=["platform", "is_active"], name="pd_platform_active_idx"),
            models.Index(fields=["user", "is_active"], name="pd_user_active_idx"),
            models.Index(fields=["last_used_at"], name="pd_last_used_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.user} | {self.platform} | {'✅' if self.is_active else '❌'} | {self.device_name or self.device_id[:12]}"
