# apps/notification/selectors/notification_selectors.py
"""
Read-only queries for the Notification domain.
All selectors return QuerySets or scalar values — never mutate state.
"""

from django.db.models import QuerySet
from apps.notification.models import Notification, NotificationChannel


def get_user_notifications(
    user_id,
    *,
    channel: str = NotificationChannel.IN_APP,
    unread_only: bool = False,
    limit: int = 50,
) -> QuerySet:
    """
    Return a user's notification feed, newest first.

    Args:
        user_id: UUID of the recipient.
        channel: Filter by delivery channel (default: in_app).
        unread_only: If True, only return unread notifications.
        limit: Maximum number of records to return.
    """
    qs = Notification.objects.filter(
        recipient_id=user_id,
        channel=channel,
    ).select_related("recipient").order_by("-created_at")

    if unread_only:
        qs = qs.filter(read_at__isnull=True)

    return qs[:limit]


def get_unread_count(user_id) -> int:
    """Return the count of unread in-app notifications for a user."""
    return Notification.objects.filter(
        recipient_id=user_id,
        channel=NotificationChannel.IN_APP,
        read_at__isnull=True,
    ).count()


def get_notification_by_id(notification_id, user_id) -> Notification | None:
    """
    Fetch a single notification by ID, scoped to the requesting user.
    Returns None if not found or if the user doesn't own it.
    """
    return Notification.objects.filter(
        id=notification_id,
        recipient_id=user_id,
    ).first()
