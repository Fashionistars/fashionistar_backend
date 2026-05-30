"""
JWT-aware authentication middleware for Django Channels.

The frontend passes the same SimpleJWT access token used by DRF in the
WebSocket query string. This middleware resolves that token into the
authenticated ``UnifiedUser`` before the consumer runs.

Bug fix (2026-05-30):
  - Use database_sync_to_async correctly with a proper function (not lambda)
    to avoid Django app-loading race condition on cold start.
  - Log the specific exception so 403s are debuggable.
  - Validate user_id as UUID string before ORM query to avoid implicit cast errors.
  - Return AnonymousUser() gracefully on any validation failure.
"""

from __future__ import annotations

import logging
import uuid
from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from channels.middleware import BaseMiddleware

logger = logging.getLogger(__name__)


def _get_user_sync(user_id_str: str):
    """
    Synchronous user lookup — called via database_sync_to_async.

    Runs inside a thread pool so Django's DB connection is valid.
    Imports are deferred here so this runs AFTER app registry is ready.
    """
    from django.contrib.auth.models import AnonymousUser
    from apps.authentication.models import UnifiedUser

    try:
        uid = uuid.UUID(str(user_id_str))  # validate UUID format before ORM query
    except (ValueError, AttributeError):
        return AnonymousUser()

    user = UnifiedUser.objects.filter(pk=uid, is_active=True).first()
    return user or AnonymousUser()


class JWTQueryAuthMiddleware(BaseMiddleware):
    """Attach ``scope['user']`` from ``?token=<access_token>`` when present."""

    async def __call__(self, scope, receive, send):
        scope["user"] = await self._resolve_user(scope)
        return await super().__call__(scope, receive, send)

    async def _resolve_user(self, scope):
        """
        Resolve the WebSocket user or fall back to ``AnonymousUser``.

        Token flow:
          1. Parse ?token= from WebSocket query string
          2. Decode with SimpleJWT AccessToken (verifies signature + expiry)
          3. Extract user_id claim
          4. Validate UUID format
          5. Fetch UnifiedUser from DB (is_active=True filter)
          6. Return user or AnonymousUser on any failure
        """
        from django.contrib.auth.models import AnonymousUser
        from rest_framework_simplejwt.tokens import AccessToken
        from rest_framework_simplejwt.exceptions import TokenError, InvalidToken

        query_string = scope.get("query_string", b"")
        if isinstance(query_string, bytes):
            query_string = query_string.decode("utf-8", errors="replace")

        token_str = parse_qs(query_string).get("token", [None])[0]
        if not token_str:
            return scope.get("user", AnonymousUser())

        try:
            decoded = AccessToken(token_str)
            user_id = decoded.get("user_id")
            if not user_id:
                logger.debug("WS auth: token missing user_id claim")
                return AnonymousUser()

            user = await database_sync_to_async(_get_user_sync)(str(user_id))
            if hasattr(user, "is_authenticated") and user.is_authenticated:
                logger.debug("WS auth: resolved user_id=%s", user_id)
            else:
                logger.debug("WS auth: user_id=%s not found or inactive", user_id)
            return user

        except (TokenError, InvalidToken) as exc:
            logger.debug("WS auth: invalid token — %s", exc)
            return AnonymousUser()
        except Exception as exc:
            # Log the real exception — previously was silently swallowed causing 403 floods
            logger.warning("WS auth: unexpected error resolving token — %s: %s", type(exc).__name__, exc)
            return AnonymousUser()
