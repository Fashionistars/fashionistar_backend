"""
WebSocket routes for real-time notification updates.
"""

from django.urls import path

from apps.notification.consumers import NotificationBadgeConsumer

websocket_urlpatterns = [
    path(
        "ws/notifications/",
        NotificationBadgeConsumer.as_asgi(),
        name="ws-notification-badge",
    ),
]
