# apps/notification/models/__init__.py
from apps.notification.models.notification import (
    Notification,
    NotificationChannel,
    NotificationType,
    NotificationTemplate,
    NotificationPreference,
)

__all__ = [
    "Notification",
    "NotificationChannel",
    "NotificationType",
    "NotificationTemplate",
    "NotificationPreference",
]

