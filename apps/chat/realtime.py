"""
Post-commit fanout helpers for the chat domain.
"""

from __future__ import annotations

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from apps.chat.models import ChatOffer, Conversation, Message


def _conversation_group(conversation_id) -> str:
    """Return the canonical Channels group name for a conversation."""
    return f"chat_conversation_{conversation_id}"


def broadcast_message_created(message_id) -> None:
    """Push a committed message into the conversation WebSocket group."""
    channel_layer = get_channel_layer()
    if channel_layer is None:
        return

    message = (
        Message.objects.select_related("author", "conversation")
        .filter(id=message_id)
        .first()
    )
    if not message:
        return

    payload = {
        "conversation_id": str(message.conversation_id),
        "message": {
            "id": str(message.id),
            "message_type": message.message_type,
            "body": message.body,
            "author_id": str(message.author_id) if message.author_id else None,
            "author_name": (
                message.author.get_full_name() or message.author.email
                if message.author
                else "Deleted User"
            ),
            "is_read_by_buyer": message.is_read_by_buyer,
            "is_read_by_vendor": message.is_read_by_vendor,
            "is_deleted": message.is_deleted,
            "created_at": message.created_at.isoformat(),
        },
    }
    async_to_sync(channel_layer.group_send)(
        _conversation_group(message.conversation_id),
        {"type": "message.new", "payload": payload},
    )


def broadcast_messages_read(conversation: Conversation, reader_id, marked_read: int) -> None:
    """Push a read-receipt summary after a successful mark-read mutation."""
    channel_layer = get_channel_layer()
    if channel_layer is None:
        return

    async_to_sync(channel_layer.group_send)(
        _conversation_group(conversation.id),
        {
            "type": "message.read",
            "payload": {
                "conversation_id": str(conversation.id),
                "reader_id": str(reader_id),
                "marked_read": marked_read,
            },
        },
    )


def broadcast_offer_updated(offer_id) -> None:
    """Push an offer-status update into the conversation room."""
    channel_layer = get_channel_layer()
    if channel_layer is None:
        return

    offer = ChatOffer.objects.select_related("conversation").filter(id=offer_id).first()
    if not offer:
        return

    async_to_sync(channel_layer.group_send)(
        _conversation_group(offer.conversation_id),
        {
            "type": "offer.update",
            "payload": {
                "conversation_id": str(offer.conversation_id),
                "offer_id": str(offer.id),
                "status": offer.status,
                "responded_at": (
                    offer.responded_at.isoformat() if offer.responded_at else None
                ),
            },
        },
    )
