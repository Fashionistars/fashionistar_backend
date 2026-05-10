"""
JWT-aware authentication middleware for Django Channels.

The frontend passes the same SimpleJWT access token used by DRF in the
WebSocket query string. This middleware resolves that token into the
authenticated ``UnifiedUser`` before the consumer runs.
"""

from __future__ import annotations

from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from channels.middleware import BaseMiddleware
from django.contrib.auth.models import AnonymousUser
from rest_framework_simplejwt.tokens import AccessToken

from apps.authentication.models import UnifiedUser


class JWTQueryAuthMiddleware(BaseMiddleware):
    """Attach ``scope['user']`` from ``?token=<access_token>`` when present."""

    async def __call__(self, scope, receive, send):
        scope["user"] = await self._resolve_user(scope)
        return await super().__call__(scope, receive, send)

    async def _resolve_user(self, scope):
        """Resolve the WebSocket user or fall back to ``AnonymousUser``."""
        query_string = scope.get("query_string", b"").decode("utf-8")
        token = parse_qs(query_string).get("token", [None])[0]
        if not token:
            return scope.get("user", AnonymousUser())

        try:
            decoded = AccessToken(token)
            user_id = decoded.get("user_id")
            if not user_id:
                return AnonymousUser()
            user = await database_sync_to_async(
                lambda: UnifiedUser.objects.filter(pk=user_id, is_active=True).first()
            )()
            return user or AnonymousUser()
        except Exception:
            return AnonymousUser()
