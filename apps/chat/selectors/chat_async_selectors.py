# apps/chat/selectors/chat_async_selectors.py
"""
Async read-only query helpers for the Chat domain.

Architecture:
  - All selectors are native async (Django 6.0 ORM).
  - ZERO sync_to_async — pure async iteration and await-able terminal calls.
  - Consumed exclusively by the Django-Ninja async router.

Selector surface:
  aget_user_conversations      → Paginated conversation feed, newest-first.
  aget_conversation_messages   → Cursor-paginated message thread.
  aget_unread_conversation_count → Badge count of threads with unread messages.
  aget_pending_offer           → Most recent PENDING offer in a conversation.
  aget_conversation_or_none    → Participant-scoped conversation fetch.
"""

import logging
import uuid
from typing import Optional

from django.db.models import Q

from apps.authentication.models import UnifiedUser
from apps.chat.models import (
    Conversation,
    ConversationStatus,
    Message,
    ChatOffer,
    OfferStatus,
)

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════
#  CONVERSATION SELECTORS
# ══════════════════════════════════════════════════════════════════════


async def aget_user_conversations(
    user: UnifiedUser,
    *,
    limit: int = 30,
    offset: int = 0,
) -> list[Conversation]:
    """
    Return a user's conversation feed (as buyer or vendor), newest-first.

    ZERO sync_to_async — uses Django 6.0 native async ORM iteration.
    The union is resolved at the Python level since Django ORM union()
    cannot always be cleanly iterated asynchronously.

    Args:
        user: The authenticated user (buyer or vendor).
        limit: Max records to return.
        offset: Pagination offset.
    """
    qs = (
        Conversation.objects.filter(Q(buyer=user) | Q(vendor=user))
        .select_related("buyer", "vendor")
        .order_by("-last_message_at", "-created_at")
    )
    return [conv async for conv in qs[offset : offset + limit]]


async def aget_conversation_or_none(
    conversation_id: str | uuid.UUID,
    user: UnifiedUser,
) -> Optional[Conversation]:
    """
    Fetch a single conversation scoped to the requesting user (participant check).
    Returns None if not found or user is not a participant.
    """
    try:
        conv = await Conversation.objects.select_related("buyer", "vendor").aget(
            id=conversation_id
        )
    except Conversation.DoesNotExist:
        return None

    if user.id not in (conv.buyer_id, conv.vendor_id):
        logger.warning(
            "aget_conversation_or_none: non-participant access attempt "
            "conversation=%s user=%s",
            conversation_id,
            user.id,
        )
        return None
    return conv


async def aget_unread_conversation_count(user: UnifiedUser) -> int:
    """
    Return the number of conversations with at least one unread message
    for the authenticated user (either as buyer or vendor).

    Used by the Ninja badge endpoint — polled by the frontend notification bar.
    """
    buyer_unread = await Conversation.objects.filter(
        buyer=user,
        unread_buyer_count__gt=0,
        status=ConversationStatus.ACTIVE,
    ).acount()

    vendor_unread = await Conversation.objects.filter(
        vendor=user,
        unread_vendor_count__gt=0,
        status=ConversationStatus.ACTIVE,
    ).acount()

    return buyer_unread + vendor_unread


# ══════════════════════════════════════════════════════════════════════
#  MESSAGE SELECTORS
# ══════════════════════════════════════════════════════════════════════


async def aget_conversation_messages(
    conversation: Conversation,
    *,
    page_size: int = 50,
    before_id: Optional[str] = None,
) -> list[Message]:
    """
    Cursor-paginated message thread for a conversation, newest-first.

    Args:
        conversation: The Conversation instance to fetch messages for.
        page_size: Max records per page.
        before_id: UUID string — if provided, return only messages older than this.

    ZERO sync_to_async — uses Django 6.0 native async ORM iteration.
    """
    qs = (
        Message.objects.filter(conversation=conversation, is_deleted=False)
        .select_related("author")
        .order_by("-created_at")
    )

    if before_id:
        try:
            pivot_qs = Message.objects.filter(id=before_id).values_list(
                "created_at", flat=True
            )
            pivot_list = [ts async for ts in pivot_qs[:1]]
            if pivot_list:
                qs = qs.filter(created_at__lt=pivot_list[0])
        except Exception:
            logger.warning(
                "aget_conversation_messages: invalid before_id=%s — ignored.",
                before_id,
            )

    return [msg async for msg in qs[:page_size]]


async def aget_unread_message_count(
    conversation: Conversation, user: UnifiedUser
) -> int:
    """
    Return the unread message count for a specific conversation participant.
    Reads the denormalized counter from the Conversation model for O(1) performance.
    """
    await conversation.arefresh_from_db(fields=["unread_buyer_count", "unread_vendor_count"])
    if user.id == conversation.buyer_id:
        return conversation.unread_buyer_count
    if user.id == conversation.vendor_id:
        return conversation.unread_vendor_count
    return 0


# ══════════════════════════════════════════════════════════════════════
#  OFFER SELECTORS
# ══════════════════════════════════════════════════════════════════════


async def aget_pending_offer(
    conversation: Conversation,
) -> Optional[ChatOffer]:
    """
    Return the most recent PENDING offer in a conversation, or None.
    Used by the chat UI to show the active offer banner.
    """
    try:
        return await ChatOffer.objects.filter(
            conversation=conversation,
            status=OfferStatus.PENDING,
        ).order_by("-created_at").afirst()
    except Exception:
        return None
