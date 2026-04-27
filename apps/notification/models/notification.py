# apps/notification/models/notification.py
"""
Notification domain models for Fashionistar.

Architecture:
  - Notification: one row per notification event sent to a user.
  - NotificationChannel: delivery channel (in_app, email, push, sms).
  - NotificationTemplate: reusable template for notification content.
  - NotificationPreference: per-user opt-in/opt-out settings per channel.

Design decisions:
  - SET_NULL on user: notification history preserved for analytics/audit
    even after account deletion (GDPR/CCPA compliant — data anonymised).
  - All financial/order notifications MUST be retained (regulatory).
  - `read_at` is NULL until the user views the notification.
  - `metadata` (JSONField) stores context (order_id, product_slug, etc.)
    without requiring FK coupling across domains.
"""

import logging

from django.contrib.auth import get_user_model
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.common.models import TimeStampedModel

User = get_user_model()
logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# DELIVERY CHANNEL ENUM
# ─────────────────────────────────────────────────────────────────────────────

class NotificationChannel(models.TextChoices):
    IN_APP = "in_app",   _("In-App")
    EMAIL  = "email",    _("Email")
    PUSH   = "push",     _("Push Notification")
    SMS    = "sms",      _("SMS")


# ─────────────────────────────────────────────────────────────────────────────
# NOTIFICATION TYPE ENUM
# ─────────────────────────────────────────────────────────────────────────────

class NotificationType(models.TextChoices):
    # Order lifecycle
    ORDER_PLACED            = "order_placed",            _("Order Placed")
    ORDER_PAYMENT_CONFIRMED = "order_payment_confirmed", _("Payment Confirmed")
    ORDER_PROCESSING        = "order_processing",        _("Order Processing")
    ORDER_SHIPPED           = "order_shipped",           _("Order Shipped")
    ORDER_DELIVERED         = "order_delivered",         _("Order Delivered")
    ORDER_CANCELLED         = "order_cancelled",         _("Order Cancelled")
    ORDER_REFUNDED          = "order_refunded",          _("Order Refunded")
    # Vendor lifecycle
    VENDOR_APPROVED         = "vendor_approved",         _("Vendor Approved")
    VENDOR_REJECTED         = "vendor_rejected",         _("Vendor Rejected")
    PRODUCT_APPROVED        = "product_approved",        _("Product Approved")
    PRODUCT_REJECTED        = "product_rejected",        _("Product Rejected")
    # Financial
    PAYOUT_INITIATED        = "payout_initiated",        _("Payout Initiated")
    PAYOUT_COMPLETED        = "payout_completed",        _("Payout Completed")
    ESCROW_RELEASED         = "escrow_released",         _("Escrow Released")
    # Communication
    NEW_MESSAGE             = "new_message",             _("New Message")
    CHAT_OFFER              = "chat_offer",              _("Chat Offer")
    MEASUREMENT_REQUESTED   = "measurement_requested",   _("Measurement Requested")
    # System
    SYSTEM_ALERT            = "system_alert",            _("System Alert")
    PROMO                   = "promo",                   _("Promotional")
    REVIEW_REMINDER         = "review_reminder",         _("Review Reminder")
    WISHLIST_PRICE_DROP     = "wishlist_price_drop",     _("Wishlist Price Drop")


# ─────────────────────────────────────────────────────────────────────────────
# 1. NOTIFICATION TEMPLATE
# ─────────────────────────────────────────────────────────────────────────────

class NotificationTemplate(TimeStampedModel):
    """
    Reusable templates for notification content.
    Variables in title/body are resolved using Python .format(**context).

    Example body:
        "Your order #{order_number} has been placed successfully."
    """

    notification_type = models.CharField(
        max_length=60,
        choices=NotificationType.choices,
        unique=True,
        db_index=True,
    )
    channel = models.CharField(
        max_length=10,
        choices=NotificationChannel.choices,
        default=NotificationChannel.IN_APP,
    )
    title_template = models.CharField(max_length=200)
    body_template  = models.TextField()
    is_active      = models.BooleanField(default=True)

    class Meta:
        verbose_name        = _("Notification Template")
        verbose_name_plural = _("Notification Templates")
        unique_together     = [("notification_type", "channel")]

    def __str__(self):
        return f"{self.notification_type} [{self.channel}]"

    def render(self, context: dict) -> tuple[str, str]:
        """
        Render title and body using the provided context dict.
        Returns (title, body) strings.
        """
        try:
            title = self.title_template.format(**context)
            body  = self.body_template.format(**context)
        except KeyError:
            title = self.title_template
            body  = self.body_template
        return title, body


# ─────────────────────────────────────────────────────────────────────────────
# 2. NOTIFICATION
# ─────────────────────────────────────────────────────────────────────────────

class Notification(TimeStampedModel):
    """
    Single notification record delivered to a user.

    Lifecycle:
      created_at  → notification generated (may be queued for delivery)
      sent_at     → successfully dispatched to channel
      read_at     → user opened/acknowledged the notification

    Financial/order notifications must be preserved for 7 years (regulatory).
    Use soft-deletion ONLY — never hard-delete financial notification records.
    """

    recipient = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="notifications",
        help_text="SET_NULL: notification preserved after account deletion.",
    )
    notification_type = models.CharField(
        max_length=60,
        choices=NotificationType.choices,
        db_index=True,
    )
    channel = models.CharField(
        max_length=10,
        choices=NotificationChannel.choices,
        default=NotificationChannel.IN_APP,
        db_index=True,
    )

    # Content (either rendered from template or provided directly)
    title = models.CharField(max_length=300)
    body  = models.TextField()

    # Cross-domain reference without FK coupling
    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text=(
            "Context data for this notification. "
            "E.g. {'order_id': '...', 'order_number': 'FSN-ORD-ABC'}."
        ),
    )

    # Delivery state
    sent_at = models.DateTimeField(null=True, blank=True)
    read_at = models.DateTimeField(null=True, blank=True)

    # For push / email — track external provider message ID
    external_id = models.CharField(max_length=300, blank=True)

    # Retry handling for failed deliveries
    retry_count = models.PositiveSmallIntegerField(default=0)
    failed      = models.BooleanField(default=False)
    error_msg   = models.TextField(blank=True)

    class Meta:
        verbose_name        = _("Notification")
        verbose_name_plural = _("Notifications")
        ordering            = ["-created_at"]
        indexes             = [
            models.Index(
                fields=["recipient", "read_at"],
                name="idx_notif_recipient_read",
            ),
            models.Index(
                fields=["notification_type", "channel"],
                name="idx_notif_type_channel",
            ),
            models.Index(
                fields=["created_at"],
                name="idx_notif_created_at",
            ),
        ]

    def __str__(self):
        return f"{self.notification_type} → {self.recipient_id} [{self.channel}]"

    @property
    def is_read(self) -> bool:
        return self.read_at is not None

    @property
    def is_sent(self) -> bool:
        return self.sent_at is not None


# ─────────────────────────────────────────────────────────────────────────────
# 3. NOTIFICATION PREFERENCE
# ─────────────────────────────────────────────────────────────────────────────

class NotificationPreference(TimeStampedModel):
    """
    Per-user opt-in/opt-out settings for each notification type per channel.

    Default: all channels enabled.
    Users can disable specific channels for specific notification types.

    Note: Financial/compliance notifications (ORDER_*, PAYOUT_*, ESCROW_*)
    cannot be disabled — enforced at the service layer.
    """

    FINANCIAL_TYPES = {
        NotificationType.ORDER_PLACED,
        NotificationType.ORDER_PAYMENT_CONFIRMED,
        NotificationType.ORDER_CANCELLED,
        NotificationType.ORDER_REFUNDED,
        NotificationType.PAYOUT_COMPLETED,
        NotificationType.ESCROW_RELEASED,
    }

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="notification_preferences",
    )
    notification_type = models.CharField(
        max_length=60,
        choices=NotificationType.choices,
    )
    channel = models.CharField(
        max_length=10,
        choices=NotificationChannel.choices,
    )
    enabled = models.BooleanField(default=True)

    class Meta:
        verbose_name        = _("Notification Preference")
        verbose_name_plural = _("Notification Preferences")
        unique_together     = [("user", "notification_type", "channel")]

    def __str__(self):
        state = "ON" if self.enabled else "OFF"
        return f"{self.user} | {self.notification_type} | {self.channel} | {state}"
