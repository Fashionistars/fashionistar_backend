"""
backend/asgi.py
================
ASGI application entrypoint for Fashionistar.

HTTP requests stay on Django's standard ASGI app. WebSocket traffic is routed
through the modular app registry with JWT query-string authentication.

Settings module priority:
  1. DJANGO_SETTINGS_MODULE environment variable (set by Dockerfile in prod).
  2. Falls back to development settings for local ``uvicorn backend.asgi:application``.
"""

import os

from channels.routing import ProtocolTypeRouter, URLRouter
from django.core.asgi import get_asgi_application

# setdefault only fires when DJANGO_SETTINGS_MODULE is NOT already in the
# environment.  The production Dockerfile sets it to backend.config.production,
# so this default only applies to local development runs.
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.config.development")

django_asgi_app = get_asgi_application()

from backend.websocket_auth import JWTQueryAuthMiddleware  # noqa: E402
from backend.websocket_routes import websocket_urlpatterns  # noqa: E402

application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        "websocket": JWTQueryAuthMiddleware(URLRouter(websocket_urlpatterns)),
    }
)

