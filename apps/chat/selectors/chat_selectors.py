"""
apps/chat/selectors/chat_selectors.py
Read-only query helpers for the Chat domain.
All selectors return QuerySets — no mutations.
"""
from django.db.models import QuerySet, Prefetch
from apps.authentication.models import UnifiedUser
from apps.chat.models import Conversation, ConversationStatus, Message


def get_user_conversations(user: UnifiedUser) -> QuerySet[Conversation]:
    """All conversations the user participates in (buyer or vendor), ordered by recency."""
    return (
        Conversation.objects
        .filter(buyer=user)
        | Conversation.objects.filter(vendor=user)
    ).prefetch_related(
        Prefetch(
            "messages",
            queryset=Message.objects.filter(is_deleted=False).order_by("-created_at")[:1],
            to_attr="_last_messages",
        )
    ).select_related("buyer", "vendor").order_by("-last_message_at")


def get_conversation_messages(
    conversation: Conversation,
    page_size: int = 50,
    before_id=None,
) -> QuerySet[Message]:
    """
    Paginated messages for a conversation (cursor-based, newest-first).
    before_id: UUID — if provided, return only messages older than this ID.
    """
    qs = Message.objects.filter(
        conversation=conversation,
        is_deleted=False,
    ).select_related("author", "media", "offer").order_by("-created_at")

    if before_id:
        pivot = Message.objects.filter(id=before_id).values_list("created_at", flat=True).first()
        if pivot:
            qs = qs.filter(created_at__lt=pivot)

    return qs[:page_size]


def get_active_offer(conversation: Conversation):
    """Return the most recent pending offer for a conversation, or None."""
    return conversation.offers.filter(status="pending").order_by("-created_at").first()
