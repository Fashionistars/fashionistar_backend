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
        """Keep startup side-effect free for explicit EventBus/on_commit flows."""
        return None
