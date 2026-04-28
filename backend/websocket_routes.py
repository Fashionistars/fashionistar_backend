"""
Central WebSocket route registry for modular backend apps.
"""

from apps.chat.routing import websocket_urlpatterns as chat_websocket_urlpatterns
from apps.notification.routing import (
    websocket_urlpatterns as notification_websocket_urlpatterns,
)

websocket_urlpatterns = [
    *chat_websocket_urlpatterns,
    *notification_websocket_urlpatterns,
]
