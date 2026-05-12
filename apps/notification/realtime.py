"""
Post-commit fanout helpers for notification badge updates.
"""

from __future__ import annotations

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from apps.notification.models import Notification, NotificationChannel


def push_unread_badge_count(user_id) -> None:
    """Push the latest unread in-app count to the user's socket group."""
    channel_layer = get_channel_layer()
    if channel_layer is None:
        return

    unread_count = Notification.objects.filter(
        recipient_id=user_id,
        channel=NotificationChannel.IN_APP,
        read_at__isnull=True,
    ).count()
    async_to_sync(channel_layer.group_send)(
        f"notification_user_{user_id}",
        {
            "type": "notification.badge",
            "payload": {"unread_count": unread_count},
        },
    )
