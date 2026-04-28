"""
Channels consumers for notification badge updates.
"""

from __future__ import annotations

from channels.generic.websocket import AsyncJsonWebsocketConsumer

from apps.notification.selectors import aget_unread_count


class NotificationBadgeConsumer(AsyncJsonWebsocketConsumer):
    """Push unread badge-count changes to the authenticated user."""

    async def connect(self):
        """Authorize the socket, join the user group, and send the first count."""
        user = self.scope.get("user")
        if not user or not user.is_authenticated:
            await self.close(code=4401)
            return

        self.group_name = f"notification_user_{user.id}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

        unread_count = await aget_unread_count(user.id)
        await self.send_json(
            {"type": "notification.badge", "payload": {"unread_count": unread_count}}
        )

    async def disconnect(self, close_code):
        """Leave the user badge group on disconnect."""
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def notification_badge(self, event):
        """Forward badge-count payloads to the browser."""
        await self.send_json(
            {"type": "notification.badge", "payload": event["payload"]}
        )
