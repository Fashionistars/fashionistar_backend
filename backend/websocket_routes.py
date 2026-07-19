"""
Central WebSocket route registry for modular backend apps.
"""

from apps.chat.routing import websocket_urlpatterns as chat_websocket_urlpatterns
from apps.notification.routing import (
    websocket_urlpatterns as notification_websocket_urlpatterns,
)
from apps.analytics.routing import (
    websocket_urlpatterns as analytics_websocket_urlpatterns,
)
# GAP-4 FIX: Real-time scan progress WebSocket consumer
from apps.measurements.ws.routing import (
    websocket_urlpatterns as scan_websocket_urlpatterns,
)

websocket_urlpatterns = [
    *chat_websocket_urlpatterns,
    *notification_websocket_urlpatterns,
    *analytics_websocket_urlpatterns,
    *scan_websocket_urlpatterns,      # GAP-4 FIX: ws/scan/<session_id>/
]

