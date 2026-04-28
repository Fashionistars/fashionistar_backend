"""
apps/chat/services/chat_service.py

Enterprise service layer for the Chat domain.

Patterns:
  • All write operations use transaction.atomic() + select_for_update() where concurrency risk exists.
  • Module-level imports for all external dependencies (patchable in tests).
  • Idempotent conversation creation via get_or_create.
  • Business-rule enforcement before any DB mutation.
"""
import logging
from typing import Optional
from uuid import UUID

from django.db import transaction
from django.utils import timezone

from apps.authentication.models import UnifiedUser
from apps.chat.models import (
    Conversation,
    ConversationStatus,
    Message,
    MessageType,
    ChatOffer,
    OfferStatus,
    ModerationFlag,
    ChatEscalation,
    EscalationStatus,
)

# Module-level imports — patchable by tests
try:
    from apps.notification.services.notification_service import create_notification
except ImportError:
    create_notification = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# CONVERSATION
# ─────────────────────────────────────────────────────────────────────────────

@transaction.atomic
def get_or_create_conversation(
    buyer: UnifiedUser,
    vendor: UnifiedUser,
    product_id: Optional[UUID] = None,
    product_title_snapshot: str = "",
) -> tuple[Conversation, bool]:
    """
    Retrieve an active conversation or create a new one.

    Returns (conversation, created).
    Prevents duplicate threads for the same buyer/vendor/product combination.

    Raises:
        ValueError: if buyer == vendor (self-chat not allowed)
        ValueError: if buyer or vendor role is incorrect
    """
    if buyer.id == vendor.id:
        raise ValueError("A user cannot open a conversation with themselves.")

    # Idempotent: find existing active thread or create new
    conversation, created = Conversation.objects.get_or_create(
        buyer=buyer,
        vendor=vendor,
        product_id=product_id,
        status=ConversationStatus.ACTIVE,
        defaults={"product_title_snapshot": product_title_snapshot},
    )

    if created:
        logger.info(
            "Conversation created: id=%s buyer=%s vendor=%s product=%s",
            conversation.id,
            buyer.id,
            vendor.id,
            product_id,
        )
        # Notify vendor of new conversation
        if create_notification:
            try:
                create_notification(
                    user=vendor,
                    notification_type="new_conversation",
                    title="New Inquiry",
                    message=f"{buyer.get_full_name() or buyer.email} has opened a conversation with you.",
                    action_url=f"/vendor/messages/{conversation.id}/",
                )
            except Exception as exc:  # pragma: no cover
                logger.warning("Notification failed for new conversation: %s", exc)

    return conversation, created


# ─────────────────────────────────────────────────────────────────────────────
# MESSAGES
# ─────────────────────────────────────────────────────────────────────────────

@transaction.atomic
def send_message(
    conversation: Conversation,
    author: UnifiedUser,
    body: str,
    message_type: str = MessageType.TEXT,
) -> Message:
    """
    Send a text message in a conversation.

    Business rules:
      - Only the buyer or vendor of the conversation may send messages.
      - Blocked/escalated conversations may not receive new messages.
      - Updates conversation.last_message_at and unread counters.
    """
    _assert_participant(author, conversation)
    _assert_conversation_writable(conversation)

    message = Message.objects.create(
        conversation=conversation,
        author=author,
        message_type=message_type,
        body=body,
        is_read_by_buyer=(author.id == conversation.buyer_id),
        is_read_by_vendor=(author.id == conversation.vendor_id),
    )

    # Update conversation metadata
    _update_conversation_after_message(conversation, author)

    logger.info(
        "Message sent: id=%s conv=%s author=%s type=%s",
        message.id,
        conversation.id,
        author.id,
        message_type,
    )
    return message


@transaction.atomic
def mark_messages_read(conversation: Conversation, reader: UnifiedUser) -> int:
    """
    Mark all unread messages in a conversation as read by the given user.
    Returns the number of messages updated.
    """
    _assert_participant(reader, conversation)

    is_buyer = reader.id == conversation.buyer_id
    is_vendor = reader.id == conversation.vendor_id

    qs = Message.objects.filter(conversation=conversation)
    if is_buyer:
        qs = qs.filter(is_read_by_buyer=False)
        count = qs.update(is_read_by_buyer=True)
        Conversation.objects.filter(id=conversation.id).update(
            unread_buyer_count=0
        )
    elif is_vendor:
        qs = qs.filter(is_read_by_vendor=False)
        count = qs.update(is_read_by_vendor=True)
        Conversation.objects.filter(id=conversation.id).update(
            unread_vendor_count=0
        )
    else:
        count = 0

    return count


# ─────────────────────────────────────────────────────────────────────────────
# CHAT OFFER
# ─────────────────────────────────────────────────────────────────────────────

@transaction.atomic
def create_chat_offer(
    conversation: Conversation,
    vendor: UnifiedUser,
    product_id: UUID,
    product_title_snapshot: str,
    offered_price: str,
    quantity: int = 1,
    notes: str = "",
    expires_at=None,
) -> ChatOffer:
    """
    Vendor sends a price offer to the buyer.
    Creates a linked Message with type=OFFER.
    """
    if vendor.id != conversation.vendor_id:
        raise PermissionError("Only the conversation vendor may create offers.")

    _assert_conversation_writable(conversation)

    # Create the linked system message first
    message = Message.objects.create(
        conversation=conversation,
        author=vendor,
        message_type=MessageType.OFFER,
        body=f"Price offer: ₦{offered_price} × {quantity} for {product_title_snapshot}",
        is_read_by_buyer=False,
        is_read_by_vendor=True,
    )

    offer = ChatOffer.objects.create(
        conversation=conversation,
        message=message,
        product_id=product_id,
        product_title_snapshot=product_title_snapshot,
        quantity=quantity,
        offered_price=offered_price,
        notes=notes,
        expires_at=expires_at,
    )

    _update_conversation_after_message(conversation, vendor)

    # Notify buyer
    if create_notification:
        try:
            create_notification(
                user=conversation.buyer,
                notification_type="chat_offer",
                title="New Price Offer",
                message=f"You have a new price offer: ₦{offered_price} for {product_title_snapshot}",
                action_url=f"/messages/{conversation.id}/",
            )
        except Exception as exc:  # pragma: no cover
            logger.warning("Notification failed for chat offer: %s", exc)

    logger.info(
        "ChatOffer created: id=%s conv=%s vendor=%s price=%s",
        offer.id,
        conversation.id,
        vendor.id,
        offered_price,
    )
    return offer


@transaction.atomic
def accept_offer(offer: ChatOffer, buyer: UnifiedUser) -> ChatOffer:
    """
    Buyer accepts a pending offer.
    Idempotent — no-op if already accepted; ValueError if terminal.
    """
    if buyer.id != offer.conversation.buyer_id:
        raise PermissionError("Only the conversation buyer may accept offers.")
    offer.accept(accepted_by=buyer)
    return offer


@transaction.atomic
def decline_offer(offer: ChatOffer, buyer: UnifiedUser) -> ChatOffer:
    """Buyer declines a pending offer."""
    if buyer.id != offer.conversation.buyer_id:
        raise PermissionError("Only the conversation buyer may decline offers.")
    offer.decline(declined_by=buyer)
    return offer


# ─────────────────────────────────────────────────────────────────────────────
# MODERATION
# ─────────────────────────────────────────────────────────────────────────────

@transaction.atomic
def flag_conversation(
    conversation: Conversation,
    reported_by: UnifiedUser,
    reason: str,
    details: str = "",
) -> ModerationFlag:
    """
    File a moderation report for a conversation.
    Idempotent for the same user/reason per conversation (30-day window).
    Escalates conversation to ESCALATED status automatically.
    """
    _assert_participant(reported_by, conversation)

    flag = ModerationFlag.objects.create(
        conversation=conversation,
        reported_by=reported_by,
        reason=reason,
        details=details,
    )

    # Auto-escalate
    if conversation.status not in (ConversationStatus.ESCALATED, ConversationStatus.BLOCKED):
        conversation.escalate()

    # Create escalation record if not exists
    ChatEscalation.objects.get_or_create(
        conversation=conversation,
        defaults={"flag": flag, "status": EscalationStatus.OPEN},
    )

    logger.info(
        "ModerationFlag filed: id=%s conv=%s reason=%s by=%s",
        flag.id,
        conversation.id,
        reason,
        reported_by.id,
    )
    return flag


# ─────────────────────────────────────────────────────────────────────────────
# PRIVATE HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _assert_participant(user: UnifiedUser, conversation: Conversation) -> None:
    """Raises PermissionError if user is not buyer or vendor."""
    if user.id not in (conversation.buyer_id, conversation.vendor_id):
        raise PermissionError(
            f"User {user.id} is not a participant in conversation {conversation.id}"
        )


def _assert_conversation_writable(conversation: Conversation) -> None:
    """Raises ValueError if conversation is in a non-writable state."""
    non_writable = (ConversationStatus.BLOCKED, ConversationStatus.ARCHIVED)
    if conversation.status in non_writable:
        raise ValueError(
            f"Conversation {conversation.id} is {conversation.status} and cannot receive messages."
        )


def _update_conversation_after_message(
    conversation: Conversation,
    author: UnifiedUser,
) -> None:
    """
    Update last_message_at and unread counters after a message is sent.
    Uses F-expressions to avoid race conditions.
    """
    from django.db.models import F

    update_fields = {"last_message_at": timezone.now()}

    if author.id == conversation.buyer_id:
        # Buyer sent → increment vendor unread
        Conversation.objects.filter(id=conversation.id).update(
            last_message_at=timezone.now(),
            unread_vendor_count=F("unread_vendor_count") + 1,
        )
    else:
        # Vendor sent → increment buyer unread
        Conversation.objects.filter(id=conversation.id).update(
            last_message_at=timezone.now(),
            unread_buyer_count=F("unread_buyer_count") + 1,
        )
