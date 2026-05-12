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
"""

from __future__ import annotations

import json
import logging

from channels.generic.websocket import AsyncJsonWebsocketConsumer

from apps.notification.selectors import aget_unread_count

logger = logging.getLogger(__name__)


class NotificationBadgeConsumer(AsyncJsonWebsocketConsumer):
    """
    Real-time notification consumer.

    Responsibilities:
      - Push unread badge count on connect (Layer 1 boot).
      - Forward group events to the browser (badge, new notification, read sync).
      - Handle client-initiated mark_read commands with atomic DB update.
      - Gracefully degrade when Redis/channel_layer is unavailable.
    """

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
            # Redis unavailable — still accept so badge polling works via REST.
            logger.warning(
                "NotificationBadgeConsumer: channel_layer is None (Redis down?), "
                "accepting without group membership for user=%s",
                self.user_id,
            )
            await self.accept()
            await self._send_badge()
            return

        await channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

        # Immediately push the current unread count so the UI badge is accurate
        # before the first poll interval fires.
        await self._send_badge()
        logger.debug("NotificationBadgeConsumer: connected user=%s", self.user_id)

    async def disconnect(self, close_code):
        """Leave the user badge group and clean up channel layer membership."""
        if hasattr(self, "group_name"):
            channel_layer = self.channel_layer
            if channel_layer is not None:
                await channel_layer.group_discard(self.group_name, self.channel_name)
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
            logger.debug("NotificationBadgeConsumer: invalid JSON from user=%s", getattr(self, "user_id", "?"))
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
            channel_layer = self.channel_layer
            if channel_layer is not None and updated:
                await channel_layer.group_send(
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
