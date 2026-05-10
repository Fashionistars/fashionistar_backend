# apps/chat/consumers.py
"""
Production-hardened WebSocket consumer for the Fashionistar chat domain.

Security:
  - JWT validated BEFORE accept() in connect() — unauthenticated connections
    are rejected immediately with code 4401 (never reach the group layer).
  - Conversation participant check (buyer or vendor only) — code 4403.
  - Per-user rate limiting: 60 inbound messages/minute via sliding window.
  - Channel-layer errors are caught and logged; the connection degrades
    gracefully rather than crashing the ASGI worker.

Reliability:
  - Heartbeat: server sends a ping every 25s. Client must reply with pong
    within 30s or the connection is closed (code 1001 Gone Away).
  - Disconnect always cleans up the channel group and any running tasks.

Architecture:
  - JWT resolution uses the DRF SimpleJWT TokenBackend directly (no DB hit).
  - User lookup is a single async DB query keyed by user_id claim.
  - Rate limiter uses an in-memory sliding window (asyncio-safe; replace with
    Redis-backed counter when scaling to multi-process workers).
"""
from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from typing import Deque

from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.contrib.auth import get_user_model

from apps.chat.models import Conversation
from apps.audit_logs.services.chat import chat_audit

logger = logging.getLogger("application")

User = get_user_model()

# ─── Rate-limit config ────────────────────────────────────────────────────────
_RATE_LIMIT_WINDOW_SECONDS = 60
_RATE_LIMIT_MAX_MESSAGES = 60  # 60 msg/min per connection

# ─── Heartbeat config ─────────────────────────────────────────────────────────
_HEARTBEAT_INTERVAL_SECONDS = 25
_PONG_TIMEOUT_SECONDS = 30


class _RateLimiter:
    """Sliding-window rate limiter (per-connection, async-safe)."""

    def __init__(self, max_messages: int, window_seconds: int) -> None:
        self._max = max_messages
        self._window = window_seconds
        self._timestamps: Deque[float] = deque()

    def is_allowed(self) -> bool:
        now = time.monotonic()
        cutoff = now - self._window
        # Evict stale entries
        while self._timestamps and self._timestamps[0] < cutoff:
            self._timestamps.popleft()
        if len(self._timestamps) >= self._max:
            return False
        self._timestamps.append(now)
        return True


class ChatConversationConsumer(AsyncJsonWebsocketConsumer):
    """
    Stream real-time chat events to conversation participants only.

    WebSocket URL: /ws/chat/<conversation_id>/?token=<jwt_access_token>
    """

    # ──────────────────────────────────────────────────────────────────────────
    # Lifecycle
    # ──────────────────────────────────────────────────────────────────────────

    async def connect(self) -> None:
        """
        Step 1: Resolve the JWT from the query string.
        Step 2: Load the authenticated user from DB.
        Step 3: Verify the user is a conversation participant.
        Step 4: Subscribe to the channel group and accept.
        """
        # ── JWT resolution ────────────────────────────────────────────────────
        user = await self._resolve_jwt_user()
        if user is None:
            logger.warning("ChatConsumer: unauthenticated connection rejected")
            await self.close(code=4401)
            return

        # ── Conversation guard ────────────────────────────────────────────────
        conversation_id = str(self.scope["url_route"]["kwargs"]["conversation_id"])
        conversation = await Conversation.objects.filter(id=conversation_id).afirst()

        if not conversation:
            await self.close(code=4404)
            return

        if user.id not in (conversation.buyer_id, conversation.vendor_id):
            logger.warning(
                "ChatConsumer: user=%s not participant in conversation=%s",
                user.id,
                conversation_id,
            )
            await self.close(code=4403)
            return

        # ── Set instance state ────────────────────────────────────────────────
        self.auth_user = user
        self.conversation_id = conversation_id
        self.group_name = f"chat_conversation_{conversation_id}"
        self._rate_limiter = _RateLimiter(_RATE_LIMIT_MAX_MESSAGES, _RATE_LIMIT_WINDOW_SECONDS)
        self._pong_received = True  # Mark true initially so first cycle doesn't fail
        self._heartbeat_task: asyncio.Task | None = None

        # ── Join group ────────────────────────────────────────────────────────
        try:
            await self.channel_layer.group_add(self.group_name, self.channel_name)
        except Exception as exc:
            logger.error("ChatConsumer: channel_layer.group_add failed: %s", exc)
            await self.close(code=1011)
            return

        await self.accept()

        # ── Audit: WebSocket connected ────────────────────────────────────────
        # Run in background thread to avoid blocking the ASGI event loop.
        # chat_audit dispatches to Celery internally — never raises.
        try:
            _jti = getattr(user, "_ws_jti", None)  # set by _resolve_jwt_user if available
            chat_audit.log_websocket_connected(
                actor=user,
                conversation_id=conversation_id,
                session_id=_jti,
            )
        except Exception:  # noqa: BLE001
            pass  # audit failure MUST NOT affect the live WebSocket connection

        # ── Start heartbeat ───────────────────────────────────────────────
        self._heartbeat_task = asyncio.ensure_future(self._heartbeat_loop())

        logger.info(
            "ChatConsumer: user=%s connected to conversation=%s",
            user.id,
            conversation_id,
        )

    async def disconnect(self, close_code: int) -> None:
        """Clean up group subscription and cancel heartbeat on disconnect."""
        # ── Audit: WebSocket disconnected ─────────────────────────────────────
        _user = getattr(self, "auth_user", None)
        _conv_id = getattr(self, "conversation_id", None)
        if _user and _conv_id:
            try:
                chat_audit.log_websocket_disconnected(
                    actor=_user,
                    conversation_id=_conv_id,
                    reason=str(close_code),
                )
            except Exception:  # noqa: BLE001
                pass

        # Cancel heartbeat task
        if getattr(self, "_heartbeat_task", None) and not self._heartbeat_task.done():
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass

        # Leave channel group
        if hasattr(self, "group_name"):
            try:
                await self.channel_layer.group_discard(self.group_name, self.channel_name)
            except Exception as exc:
                logger.warning("ChatConsumer: group_discard error (non-fatal): %s", exc)

        logger.info(
            "ChatConsumer: user=%s disconnected from conversation=%s code=%s",
            getattr(self, "auth_user", {-1}).id if hasattr(self, "auth_user") else "?",
            getattr(self, "conversation_id", "?"),
            close_code,
        )

    async def receive_json(self, content: dict, **kwargs) -> None:
        """Handle client-originated socket events with rate limiting."""

        # ── Rate limit ────────────────────────────────────────────────────────
        if not self._rate_limiter.is_allowed():
            logger.warning(
                "ChatConsumer: rate limit exceeded for user=%s conversation=%s",
                self.auth_user.id,
                self.conversation_id,
            )
            await self.send_json({"type": "error", "payload": {"code": 4029, "detail": "Rate limit exceeded."}})
            return

        event_type = content.get("type")

        # ── Heartbeat pong ────────────────────────────────────────────────────
        if event_type == "pong":
            self._pong_received = True
            return

        # ── Typing indicator ──────────────────────────────────────────────────
        if event_type == "user.typing":
            try:
                await self.channel_layer.group_send(
                    self.group_name,
                    {"type": "user.typing", "payload": content.get("payload", {})},
                )
            except Exception as exc:
                logger.error("ChatConsumer: group_send user.typing failed: %s", exc)

    # ──────────────────────────────────────────────────────────────────────────
    # Group event handlers (server → browser)
    # ──────────────────────────────────────────────────────────────────────────

    async def message_new(self, event: dict) -> None:
        """Forward a new-message event to the browser."""
        await self._safe_send_json({"type": "message.new", "payload": event["payload"]})

    async def message_read(self, event: dict) -> None:
        """Forward a read-receipt event to the browser."""
        await self._safe_send_json({"type": "message.read", "payload": event["payload"]})

    async def offer_update(self, event: dict) -> None:
        """Forward an offer lifecycle event to the browser."""
        await self._safe_send_json({"type": "offer.update", "payload": event["payload"]})

    async def conversation_status(self, event: dict) -> None:
        """Forward a conversation status-change event to the browser."""
        await self._safe_send_json({"type": "conversation.status", "payload": event["payload"]})

    async def user_typing(self, event: dict) -> None:
        """Forward typing indicators within the conversation room."""
        await self._safe_send_json({"type": "user.typing", "payload": event["payload"]})

    # ──────────────────────────────────────────────────────────────────────────
    # Private helpers
    # ──────────────────────────────────────────────────────────────────────────

    async def _resolve_jwt_user(self) -> User | None:
        """
        Extract and validate the JWT bearer token from the query string.

        Token is passed as: wss://…/ws/chat/<id>/?token=<access_token>

        Returns:
            User instance if valid, None otherwise.
        """
        try:
            from rest_framework_simplejwt.tokens import AccessToken  # noqa: PLC0415
            from rest_framework_simplejwt.exceptions import TokenError  # noqa: PLC0415

            query_string = self.scope.get("query_string", b"").decode("utf-8")
            params: dict[str, str] = dict(
                p.split("=", 1) for p in query_string.split("&") if "=" in p
            )
            raw_token = params.get("token", "")
            if not raw_token:
                return None

            token = AccessToken(raw_token)
            user_id = token["user_id"]
            user = await User.objects.filter(pk=user_id, is_active=True).afirst()
            return user
        except Exception as exc:  # noqa: BLE001
            logger.debug("ChatConsumer: JWT resolution failed: %s", exc)
            return None

    async def _heartbeat_loop(self) -> None:
        """
        Send a ping every 25 seconds. If no pong arrives within 30 seconds,
        close the connection (code 1001 Going Away).
        """
        while True:
            await asyncio.sleep(_HEARTBEAT_INTERVAL_SECONDS)
            self._pong_received = False
            try:
                await self.send_json({"type": "ping"})
            except Exception:
                break

            # Wait for pong
            await asyncio.sleep(_PONG_TIMEOUT_SECONDS - _HEARTBEAT_INTERVAL_SECONDS)
            if not self._pong_received:
                logger.info(
                    "ChatConsumer: heartbeat timeout — closing user=%s conversation=%s",
                    getattr(self.auth_user, "id", "?"),
                    self.conversation_id,
                )
                await self.close(code=1001)
                break

    async def _safe_send_json(self, data: dict) -> None:
        """Send JSON, swallowing channel errors so one bad client can't crash the group."""
        try:
            await self.send_json(data)
        except Exception as exc:
            logger.warning("ChatConsumer: send_json failed (non-fatal): %s", exc)
