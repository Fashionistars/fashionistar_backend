# apps/notification/apps.py
"""
Notification domain AppConfig.

Provides in-app notifications, email digest triggers, push-notification
dispatch, and the WebSocket real-time notification feed.
"""
from django.apps import AppConfig


class NotificationConfig(AppConfig):
    name = "apps.notification"
    label = "notification"
    verbose_name = "Notifications"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        # Import signal receivers after app registry is ready
        import apps.notification.signals  # noqa: F401  # pylint: disable=import-outside-toplevel
