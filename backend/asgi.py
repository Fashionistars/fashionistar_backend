"""
ASGI application entrypoint for Fashionistar.

HTTP requests stay on Django's standard ASGI app. WebSocket traffic is routed
through the modular app registry with JWT query-string authentication.
"""

import os

from channels.routing import ProtocolTypeRouter, URLRouter
from django.core.asgi import get_asgi_application

from backend.websocket_auth import JWTQueryAuthMiddleware
from backend.websocket_routes import websocket_urlpatterns

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.config.development")

django_asgi_app = get_asgi_application()

application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        "websocket": JWTQueryAuthMiddleware(URLRouter(websocket_urlpatterns)),
    }
)













