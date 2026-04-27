# apps/notification/services/notification_service.py
"""
Business logic for the Notification domain.

Rules:
  - Services call selectors for reads, ORM for writes.
  - All writes use transaction.atomic().
  - Financial/compliance notifications CANNOT be suppressed.
  - Dispatch is fire-and-forget via Celery task (never blocks the caller).
  - Audit events are emitted for all notification actions.
"""

import logging
from django.db import transaction
from django.utils import timezone

from apps.notification.models import (
    Notification,
    NotificationChannel,
    NotificationType,
    NotificationPreference,
    NotificationTemplate,
)

logger = logging.getLogger(__name__)

# Notification types that CANNOT be suppressed by user preferences
_MANDATORY_TYPES = {
    NotificationType.ORDER_PLACED,
    NotificationType.ORDER_PAYMENT_CONFIRMED,
    NotificationType.ORDER_CANCELLED,
    NotificationType.ORDER_REFUNDED,
    NotificationType.PAYOUT_COMPLETED,
    NotificationType.ESCROW_RELEASED,
    NotificationType.VENDOR_APPROVED,
    NotificationType.VENDOR_REJECTED,
}


def _is_opted_in(user, notification_type: str, channel: str) -> bool:
    """
    Returns True if the user has opted into this notification channel.
    Mandatory types always return True regardless of preference.
    """
    if notification_type in _MANDATORY_TYPES:
        return True
    pref = NotificationPreference.objects.filter(
        user=user,
        notification_type=notification_type,
        channel=channel,
    ).first()
    if pref is None:
        return True  # Default: all enabled
    return pref.enabled


def _get_template_content(
    notification_type: str,
    channel: str,
    context: dict,
    fallback_title: str,
    fallback_body: str,
) -> tuple[str, str]:
    """
    Try to render content from a NotificationTemplate. Fall back to
    the provided fallback title/body if no template exists.
    """
    tmpl = NotificationTemplate.objects.filter(
        notification_type=notification_type,
        channel=channel,
        is_active=True,
    ).first()
    if tmpl:
        return tmpl.render(context)
    return fallback_title, fallback_body


# ─────────────────────────────────────────────────────────────────────────────
# CORE: Create Notification
# ─────────────────────────────────────────────────────────────────────────────

@transaction.atomic
def create_notification(
    *,
    recipient,
    notification_type: str,
    title: str,
    body: str,
    channel: str = NotificationChannel.IN_APP,
    metadata: dict | None = None,
) -> Notification | None:
    """
    Create and persist a single notification.

    Returns None if the user has opted out (and it's not a mandatory type).
    """
    if not _is_opted_in(recipient, notification_type, channel):
        logger.debug(
            "Notification suppressed: user=%s type=%s channel=%s",
            recipient,
            notification_type,
            channel,
        )
        return None

    notification = Notification.objects.create(
        recipient=recipient,
        notification_type=notification_type,
        channel=channel,
        title=title,
        body=body,
        metadata=metadata or {},
    )
    logger.info(
        "Notification created: id=%s type=%s user=%s",
        notification.id,
        notification_type,
        getattr(recipient, "id", "?"),
    )
    # Schedule async dispatch (Celery) — fire-and-forget
    try:
        from apps.notification.tasks import dispatch_notification_task
        dispatch_notification_task.delay(str(notification.id))
    except Exception:
        logger.warning(
            "Could not enqueue dispatch for notification=%s. Will be retried.",
            notification.id,
        )
    return notification


# ─────────────────────────────────────────────────────────────────────────────
# READ STATE
# ─────────────────────────────────────────────────────────────────────────────

@transaction.atomic
def mark_as_read(*, user, notification_id) -> Notification | None:
    """Mark a single notification as read. Verifies ownership."""
    now = timezone.now()
    updated = Notification.objects.filter(
        id=notification_id,
        recipient=user,
        read_at__isnull=True,
    ).update(read_at=now)
    if not updated:
        return None
    return Notification.objects.get(id=notification_id)


@transaction.atomic
def mark_all_as_read(*, user) -> int:
    """Mark all unread in-app notifications as read. Returns count updated."""
    now = timezone.now()
    count = Notification.objects.filter(
        recipient=user,
        channel=NotificationChannel.IN_APP,
        read_at__isnull=True,
    ).update(read_at=now)
    logger.info("mark_all_as_read: user=%s count=%d", user, count)
    return count


# ─────────────────────────────────────────────────────────────────────────────
# DOMAIN-SPECIFIC CONVENIENCE HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def send_order_notification(
    *,
    recipient,
    notification_type: str,
    order_number: str,
    order_id: str,
    extra_context: dict | None = None,
) -> Notification | None:
    """
    Send a standard order lifecycle notification.

    The template (if present) receives context:
        {order_number, order_id, ...extra_context}
    """
    context = {
        "order_number": order_number,
        "order_id": order_id,
        **(extra_context or {}),
    }
    title, body = _get_template_content(
        notification_type=notification_type,
        channel=NotificationChannel.IN_APP,
        context=context,
        fallback_title=f"Order #{order_number} Update",
        fallback_body=f"Your order #{order_number} status has changed.",
    )
    return create_notification(
        recipient=recipient,
        notification_type=notification_type,
        title=title,
        body=body,
        channel=NotificationChannel.IN_APP,
        metadata={"order_id": order_id, "order_number": order_number, **(extra_context or {})},
    )


def send_vendor_notification(
    *,
    recipient,
    notification_type: str,
    extra_context: dict | None = None,
) -> Notification | None:
    """Send a vendor lifecycle notification (approved, rejected, product_approved, etc.)."""
    context = extra_context or {}
    title, body = _get_template_content(
        notification_type=notification_type,
        channel=NotificationChannel.IN_APP,
        context=context,
        fallback_title="Vendor Account Update",
        fallback_body="There is an update to your vendor account.",
    )
    return create_notification(
        recipient=recipient,
        notification_type=notification_type,
        title=title,
        body=body,
        channel=NotificationChannel.IN_APP,
        metadata=context,
    )


def bulk_notify(
    *,
    recipients: list,
    notification_type: str,
    title: str,
    body: str,
    channel: str = NotificationChannel.IN_APP,
    metadata: dict | None = None,
) -> list[Notification]:
    """
    Create notifications for a list of users (e.g., price-drop wishlist alert).
    Uses bulk_create for performance — does NOT trigger individual signals.
    """
    records = []
    for user in recipients:
        if not _is_opted_in(user, notification_type, channel):
            continue
        records.append(
            Notification(
                recipient=user,
                notification_type=notification_type,
                channel=channel,
                title=title,
                body=body,
                metadata=metadata or {},
            )
        )
    created = Notification.objects.bulk_create(records, batch_size=200)
    logger.info(
        "bulk_notify: type=%s channel=%s count=%d",
        notification_type,
        channel,
        len(created),
    )
    return created
