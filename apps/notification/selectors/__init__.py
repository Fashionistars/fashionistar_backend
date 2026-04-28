# apps/notification/selectors/__init__.py
from apps.notification.selectors.notification_selectors import (
    # Sync
    get_user_notifications,
    get_unread_count,
    get_notification_by_id,
    # Async (Django 6.0 native ORM — ZERO sync_to_async)
    aget_user_notifications,
    aget_unread_count,
    aget_notification_by_id,
)

__all__ = [
    # Sync
    "get_user_notifications",
    "get_unread_count",
    "get_notification_by_id",
    # Async
    "aget_user_notifications",
    "aget_unread_count",
    "aget_notification_by_id",
]
