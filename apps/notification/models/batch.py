# apps/notification/models/batch.py
"""
NotificationBatch + NotificationReadReceipt — Phase 5 notification infrastructure.

NotificationBatch:
  - Groups bulk notification sends (e.g. promotional broadcast, system alert).
  - Tracks total/sent/failed counts for operational visibility.
  - Used by the notification fan-out Celery task for progress tracking.

NotificationReadReceipt:
  - Explicit read confirmation per notification per user.
  - Decoupled from the Notification.read_at timestamp for multi-device tracking.
  - GDPR: 3-year retention (notification engagement analytics).
"""

from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.common.models import TimeStampedModel
from apps.notification.models.notification import Notification, NotificationChannel, NotificationType


# ─────────────────────────────────────────────────────────────────────────────
# NOTIFICATION BATCH
# ─────────────────────────────────────────────────────────────────────────────


class NotificationBatch(TimeStampedModel):
    """
    Bulk notification dispatch batch.

    Created by the admin or notification service before fan-out begins.
    The fan-out Celery task updates sent_count / failed_count atomically.

    Attributes:
        batch_id: UUID for external reference and idempotency.
        title: Internal label (e.g. "June 2026 Sale Promo Blast").
        notification_type: Target notification type for all messages in batch.
        channel: Target delivery channel.
        target_roles: JSON list of role slugs to fan out to. Empty = all users.
        template_context: Shared context dict merged into each notification render.
        total_count: Total recipients targeted.
        sent_count: Successfully dispatched.
        failed_count: Failed deliveries (will be retried up to max_retries).
        status: Lifecycle status of the batch.
        scheduled_at: When to begin dispatch (null = immediate).
        completed_at: When all dispatches finished.
        created_by: Staff user who initiated the batch.
    """

    class Status(models.TextChoices):
        DRAFT = "draft", _("Draft")
        SCHEDULED = "scheduled", _("Scheduled")
        SENDING = "sending", _("Sending")
        COMPLETED = "completed", _("Completed")
        FAILED = "failed", _("Failed")
        CANCELLED = "cancelled", _("Cancelled")

    batch_id = models.UUIDField(
        unique=True,
        default=uuid.uuid4,
        editable=False,
        db_index=True,
        verbose_name=_("Batch ID"),
    )
    title = models.CharField(
        max_length=200,
        verbose_name=_("Internal Title"),
        help_text=_("E.g. 'June 2026 Summer Sale Blast'."),
    )
    notification_type = models.CharField(
        max_length=60,
        choices=NotificationType.choices,
        db_index=True,
        verbose_name=_("Notification Type"),
    )
    channel = models.CharField(
        max_length=10,
        choices=NotificationChannel.choices,
        default=NotificationChannel.IN_APP,
        verbose_name=_("Channel"),
    )
    target_roles = models.JSONField(
        default=list,
        blank=True,
        verbose_name=_("Target Roles"),
        help_text=_("Role slugs to fan out to. Empty list = all active users."),
    )
    template_context = models.JSONField(
        default=dict,
        blank=True,
        verbose_name=_("Template Context"),
        help_text=_("Shared context dict for template rendering."),
    )
    total_count = models.PositiveIntegerField(
        default=0,
        verbose_name=_("Total Recipients"),
    )
    sent_count = models.PositiveIntegerField(
        default=0,
        verbose_name=_("Sent Count"),
    )
    failed_count = models.PositiveIntegerField(
        default=0,
        verbose_name=_("Failed Count"),
    )
    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.DRAFT,
        db_index=True,
        verbose_name=_("Status"),
    )
    scheduled_at = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
        verbose_name=_("Scheduled At"),
        help_text=_("Null = immediate dispatch on approval."),
    )
    completed_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("Completed At"),
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="notification_batches",
        verbose_name=_("Created By"),
    )

    class Meta:
        verbose_name = _("Notification Batch")
        verbose_name_plural = _("Notification Batches")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "scheduled_at"], name="nb_status_sched_idx"),
        ]

    def __str__(self) -> str:
        return f"[{self.status.upper()}] {self.title} ({self.sent_count}/{self.total_count})"

    @property
    def success_rate(self) -> float:
        """Percentage of successfully sent notifications in this batch."""
        if not self.total_count:
            return 0.0
        return round((self.sent_count / self.total_count) * 100, 2)


# ─────────────────────────────────────────────────────────────────────────────
# NOTIFICATION READ RECEIPT
# ─────────────────────────────────────────────────────────────────────────────


class NotificationReadReceipt(TimeStampedModel):
    """
    Explicit read confirmation for a notification, per device.

    Decoupled from Notification.read_at so multi-device read tracking
    is possible without polluting the core Notification model.

    GDPR: 3-year retention. Read receipts are analytics data.
    PII: user FK — anonymized on account deletion via SET_NULL.

    Attributes:
        notification: The notification that was read.
        user: Who read it (SET_NULL on deletion for analytics preservation).
        read_at: When the user read/acknowledged the notification.
        device_id: Optional device fingerprint for multi-device analytics.
        client_ip: For geographic analytics (anonymized after 30 days).
    """

    notification = models.ForeignKey(
        Notification,
        on_delete=models.CASCADE,
        related_name="read_receipts",
        verbose_name=_("Notification"),
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="notification_read_receipts",
        verbose_name=_("User"),
    )
    read_at = models.DateTimeField(
        db_index=True,
        verbose_name=_("Read At"),
    )
    device_id = models.CharField(
        max_length=128,
        blank=True,
        db_index=True,
        verbose_name=_("Device ID"),
        help_text=_("Client device fingerprint for multi-device tracking."),
    )
    client_ip = models.GenericIPAddressField(
        null=True,
        blank=True,
        verbose_name=_("Client IP"),
        help_text=_("Anonymized after 30 days per GDPR data minimization."),
    )

    class Meta:
        verbose_name = _("Notification Read Receipt")
        verbose_name_plural = _("Notification Read Receipts")
        ordering = ["-read_at"]
        unique_together = [("notification", "user", "device_id")]
        indexes = [
            models.Index(fields=["notification", "user"], name="nrr_notif_user_idx"),
            models.Index(fields=["user", "read_at"], name="nrr_user_read_idx"),
        ]

    def __str__(self) -> str:
        return f"ReadReceipt: {self.user} | {self.notification_id} | {self.read_at}"
