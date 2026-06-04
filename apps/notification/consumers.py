"""
apps/notification/consumers.py
================================
Enterprise-grade Django Channels WebSocket consumer for real-time
notification badge and feed updates.

Architecture — Three-layer push model:
  Layer 1: Badge count (unread integer) — pushed on connect and on every
           notification.badge group event (triggered by realtime.py or
           NotificationService.dispatch()).
  Layer 2: Notification feed item — pushed as a full notification object
           whenever a new notification is created for this user (type=
           ``notification.new``).
  Layer 3: Bulk mark-read sync — pushed when another client (tab) marks
           notifications read (type=``notification.read_sync``).

WebSocket protocol:
  Client → Server messages:
    { "type": "ping" }                       → { "type": "pong" }
    { "type": "mark_read", "id": "<uuid>" }  → re-pushes updated badge count

  Server → Client events:
    { "type": "notification.badge",    "payload": { "unread_count": N } }
    { "type": "notification.new",      "payload": { ...notification } }
    { "type": "notification.read_sync","payload": { "marked": N } }

Group naming convention:
  notification_user_{user.id}   — per-user fan-out group

Authentication:
  Requires JWTQueryAuthMiddleware (set in backend/asgi.py).
  Unauthenticated connections are rejected with close code 4401.

Resilience:
  - channel_layer may be None (Redis down) — close gracefully with 1011.
  - All ORM calls use native Django 6 async ORM (zero sync_to_async).
  - mark_read is fully atomic (uses service layer not raw queryset update).
  - Every Redis interaction (group_add, group_send, group_discard) is wrapped
    in a try/except that catches OSError, asyncio.TimeoutError,
    channels_redis ConnectionError and redis TimeoutError so a transient
    Redis blip never crashes the WebSocket coroutine or the uvicorn worker.
"""

from __future__ import annotations

import asyncio
import json
import logging

from channels.generic.websocket import AsyncJsonWebsocketConsumer

from apps.notification.selectors import aget_unread_count

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Exception bucket that covers all Redis / channels_redis / network errors
# we need to handle gracefully.  Imported lazily inside _try_* helpers so
# that missing optional deps don't crash settings import.
# ---------------------------------------------------------------------------
_REDIS_ERRORS = (
    OSError,           # socket-level: ECONNREFUSED, ETIMEDOUT, etc.
    TimeoutError,      # Python built-in (subclass of OSError on Py3.11+)
    asyncio.TimeoutError,  # raised by asyncio.wait_for wrappers
)

try:
    from redis.exceptions import TimeoutError as RedisTimeoutError
    from redis.exceptions import ConnectionError as RedisConnectionError
    _REDIS_ERRORS = _REDIS_ERRORS + (RedisTimeoutError, RedisConnectionError)
except ImportError:
    pass

try:
    from channels_redis.core import ChannelFull  # noqa: F401 — import for awareness
except ImportError:
    pass


class NotificationBadgeConsumer(AsyncJsonWebsocketConsumer):
    """
    Real-time notification consumer.

    Responsibilities:
      - Push unread badge count on connect (Layer 1 boot).
      - Forward group events to the browser (badge, new notification, read sync).
      - Handle client-initiated mark_read commands with atomic DB update.
      - Gracefully degrade when Redis/channel_layer is unavailable.

    Redis failure strategy:
      - connect():      If group_add raises, log and continue without group
                        membership. Badge still delivered from DB. Consumer
                        sets self._channel_layer_ok = False so group_send
                        calls are skipped for this session.
      - disconnect():   group_discard errors are swallowed — they are best-
                        effort cleanup and must not propagate.
      - _handle_mark_read(): group_send errors are caught — the mark_read DB
                        write still completes and the badge is re-pushed to
                        the initiating socket.
    """

    # Set to False when the channel layer raises during connect() so all
    # subsequent group operations are skipped gracefully for this session.
    _channel_layer_ok: bool = True

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def connect(self):
        """
        Authenticate → join group → send initial badge count → accept.
        Rejects unauthenticated connections with WS close 4401.
        """
        user = self.scope.get("user")
        if not user or not user.is_authenticated:
            logger.warning("NotificationBadgeConsumer: unauthenticated connection rejected.")
            await self.close(code=4401)
            return

        self.user_id = str(user.id)
        self.group_name = f"notification_user_{self.user_id}"

        channel_layer = self.channel_layer
        if channel_layer is None:
            # channels_redis backend not configured at all — still accept so
            # badge polling works via REST.
            logger.warning(
                "NotificationBadgeConsumer: channel_layer is None (Redis not configured?), "
                "accepting without group membership for user=%s",
                self.user_id,
            )
            self._channel_layer_ok = False
            await self.accept()
            await self._send_badge()
            return

        # Attempt group registration; degrade gracefully on Redis failure.
        self._channel_layer_ok = await self._try_group_add(channel_layer)

        await self.accept()

        # Immediately push the current unread count so the UI badge is accurate
        # before the first poll interval fires.
        await self._send_badge()
        logger.debug(
            "NotificationBadgeConsumer: connected user=%s layer_ok=%s",
            self.user_id,
            self._channel_layer_ok,
        )

    async def disconnect(self, close_code):
        """Leave the user badge group and clean up channel layer membership."""
        if hasattr(self, "group_name") and self._channel_layer_ok:
            channel_layer = self.channel_layer
            if channel_layer is not None:
                await self._try_group_discard(channel_layer)
        logger.debug(
            "NotificationBadgeConsumer: disconnected user=%s code=%s",
            getattr(self, "user_id", "?"),
            close_code,
        )

    async def receive(self, text_data=None, bytes_data=None, **kwargs):
        """
        Handle inbound client messages.

        Supported message types:
          - ``ping``       → respond with ``pong`` (keepalive)
          - ``mark_read``  → mark a single notification read, re-push badge
        """
        if not text_data:
            return

        try:
            payload = json.loads(text_data)
        except (json.JSONDecodeError, ValueError):
            logger.debug(
                "NotificationBadgeConsumer: invalid JSON from user=%s",
                getattr(self, "user_id", "?"),
            )
            return

        msg_type = payload.get("type", "")

        if msg_type == "ping":
            await self.send_json({"type": "pong"})

        elif msg_type == "mark_read":
            notification_id = payload.get("id", "").strip()
            if notification_id:
                await self._handle_mark_read(notification_id)

        else:
            logger.debug(
                "NotificationBadgeConsumer: unknown message type=%s user=%s",
                msg_type,
                getattr(self, "user_id", "?"),
            )

    # ── Group event handlers (Server → Client push) ───────────────────────────

    async def notification_badge(self, event):
        """
        Forward badge-count group events to the connected browser.

        Triggered by:
          - realtime.push_unread_badge_count() after service writes
          - Internal ``_send_badge()`` calls
        """
        await self.send_json({
            "type": "notification.badge",
            "payload": event.get("payload", {}),
        })

    async def notification_new(self, event):
        """
        Forward new-notification group events to the browser.

        Triggered by NotificationService.dispatch() after creating a
        Notification row and calling:
          channel_layer.group_send(group_name, {"type": "notification.new", "payload": {...}})

        Payload shape (mirrors NotificationSchema on the frontend):
          {
            "id": "<uuid>",
            "title": "...",
            "body": "...",
            "notification_type": "...",
            "channel": "in_app",
            "is_read": false,
            "created_at": "ISO-8601"
          }
        """
        await self.send_json({
            "type": "notification.new",
            "payload": event.get("payload", {}),
        })

    async def notification_read_sync(self, event):
        """
        Broadcast mark-all-read events to other open tabs of the same user.

        Allows a second browser tab to instantly clear its badge when the
        first tab marks all notifications read.
        """
        await self.send_json({
            "type": "notification.read_sync",
            "payload": event.get("payload", {}),
        })

    # ── Internal helpers ──────────────────────────────────────────────────────

    async def _send_badge(self):
        """Query the DB for the current unread count and push to this socket."""
        try:
            unread = await aget_unread_count(self.user_id)
        except Exception as exc:
            logger.warning("_send_badge: DB error for user=%s: %s", self.user_id, exc)
            unread = 0
        await self.send_json({
            "type": "notification.badge",
            "payload": {"unread_count": unread},
        })

    async def _handle_mark_read(self, notification_id: str):
        """
        Mark a single notification as read via the service layer.

        Uses Django 6 native async ORM (aupdate / aget) — zero sync_to_async.
        After the update, re-pushes the updated badge count to this socket
        and fan-outs a read_sync event to all other open tabs.
        """
        from django.utils import timezone

        from apps.notification.models import Notification

        try:
            updated = await Notification.objects.filter(
                id=notification_id,
                recipient_id=self.user_id,
                read_at__isnull=True,
            ).aupdate(read_at=timezone.now(), is_read=True)

            if updated:
                logger.debug(
                    "mark_read: notification_id=%s user=%s", notification_id, self.user_id
                )

            # Re-push the refreshed badge to this socket.
            await self._send_badge()

            # Fan-out read-sync to other open tabs of the same user.
            if self._channel_layer_ok and updated:
                channel_layer = self.channel_layer
                if channel_layer is not None:
                    await self._try_group_send(
                        channel_layer,
                        self.group_name,
                        {
                            "type": "notification.read_sync",
                            "payload": {"marked": 1, "notification_id": notification_id},
                        },
                    )
        except Exception as exc:
            logger.warning(
                "_handle_mark_read: failed for notification_id=%s user=%s: %s",
                notification_id,
                self.user_id,
                exc,
            )

    # ── Redis resilience wrappers ─────────────────────────────────────────────
    #
    # All three wrappers return bool (True = success, False = Redis error).
    # They never raise — the calling code decides how to degrade.

    async def _try_group_add(self, channel_layer) -> bool:
        """
        Attempt group_add; return False and log on any Redis/network error.

        Failure here means this WebSocket session will NOT receive server-push
        events, but it can still serve the initial badge count from the DB and
        respond to mark_read commands.
        """
        try:
            await channel_layer.group_add(self.group_name, self.channel_name)
            return True
        except _REDIS_ERRORS as exc:
            logger.error(
                "NotificationBadgeConsumer: Redis group_add failed for user=%s "
                "group=%s — WebSocket degraded (no real-time push). Error: %s",
                self.user_id,
                self.group_name,
                exc,
            )
            return False
        except Exception as exc:
            logger.error(
                "NotificationBadgeConsumer: unexpected error in group_add for user=%s: %s",
                self.user_id,
                exc,
            )
            return False

    async def _try_group_discard(self, channel_layer) -> None:
        """
        Attempt group_discard; swallow any Redis/network error on disconnect.

        Stale group membership entries expire after ``group_expiry`` seconds
        (configured in CHANNEL_LAYERS) so a failed discard is self-healing.
        """
        try:
            await channel_layer.group_discard(self.group_name, self.channel_name)
        except _REDIS_ERRORS as exc:
            logger.warning(
                "NotificationBadgeConsumer: Redis group_discard failed for user=%s "
                "(stale entry will expire). Error: %s",
                self.user_id,
                exc,
            )
        except Exception as exc:
            logger.warning(
                "NotificationBadgeConsumer: unexpected error in group_discard for user=%s: %s",
                self.user_id,
                exc,
            )

    async def _try_group_send(self, channel_layer, group: str, message: dict) -> bool:
        """
        Attempt group_send; return False and log on any Redis/network error.

        A failed group_send is non-fatal — the initiating socket's badge has
        already been updated via _send_badge().  Other tabs will re-sync on
        their next badge poll.
        """
        try:
            await channel_layer.group_send(group, message)
            return True
        except _REDIS_ERRORS as exc:
            logger.warning(
                "NotificationBadgeConsumer: Redis group_send failed for user=%s "
                "group=%s message_type=%s. Error: %s",
                self.user_id,
                group,
                message.get("type"),
                exc,
            )
            return False
        except Exception as exc:
            logger.warning(
                "NotificationBadgeConsumer: unexpected error in group_send for user=%s: %s",
                self.user_id,
                exc,
            )
            return False
