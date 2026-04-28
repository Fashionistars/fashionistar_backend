"""
Channels consumers for the modular chat domain.
"""

from __future__ import annotations

import logging

from channels.generic.websocket import AsyncJsonWebsocketConsumer

from apps.chat.models import Conversation

logger = logging.getLogger(__name__)


class ChatConversationConsumer(AsyncJsonWebsocketConsumer):
    """Stream real-time chat events to conversation participants only."""

    async def connect(self):
        """Authorize the user and subscribe them to the conversation group."""
        user = self.scope.get("user")
        conversation_id = str(self.scope["url_route"]["kwargs"]["conversation_id"])

        if not user or not user.is_authenticated:
            await self.close(code=4401)
            return

        conversation = await Conversation.objects.filter(id=conversation_id).afirst()
        if not conversation:
            await self.close(code=4404)
            return

        if user.id not in (conversation.buyer_id, conversation.vendor_id):
            await self.close(code=4403)
            return

        self.conversation_id = conversation_id
        self.group_name = f"chat_conversation_{conversation_id}"

        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        """Leave the conversation group on socket close."""
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive_json(self, content, **kwargs):
        """Handle lightweight client-originated socket events."""
        event_type = content.get("type")
        if event_type == "user.typing":
            await self.channel_layer.group_send(
                self.group_name,
                {
                    "type": "user.typing",
                    "payload": content.get("payload", {}),
                },
            )

    async def message_new(self, event):
        """Forward a new-message event to the browser."""
        await self.send_json({"type": "message.new", "payload": event["payload"]})

    async def message_read(self, event):
        """Forward a read-receipt event to the browser."""
        await self.send_json({"type": "message.read", "payload": event["payload"]})

    async def offer_update(self, event):
        """Forward an offer lifecycle event to the browser."""
        await self.send_json({"type": "offer.update", "payload": event["payload"]})

    async def conversation_status(self, event):
        """Forward a conversation status-change event to the browser."""
        await self.send_json(
            {"type": "conversation.status", "payload": event["payload"]}
        )

    async def user_typing(self, event):
        """Forward typing indicators within the conversation room."""
        await self.send_json({"type": "user.typing", "payload": event["payload"]})
