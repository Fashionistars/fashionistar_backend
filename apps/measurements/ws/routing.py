# apps/measurements/ws/routing.py
"""
WebSocket URL routing for the measurements app.
Registered in backend/websocket_routes.py.

Route:
    ws://<host>/ws/scan/<session_id>/
    ?token=<JWT>  (authenticated via JWTQueryAuthMiddleware)
"""

from django.urls import re_path
from .scan_consumer import ScanProgressConsumer

websocket_urlpatterns = [
    re_path(
        r"^ws/scan/(?P<session_id>[0-9a-f-]{36})/$",
        ScanProgressConsumer.as_asgi(),
        name="ws-scan-progress",
    ),
]
