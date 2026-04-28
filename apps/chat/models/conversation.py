"""
apps/chat/models/conversation.py
Chat domain models — Fashionistar enterprise messaging layer.

Model hierarchy:
  Conversation (1) → Message (*) → MessageMedia (*)
                   → ChatOffer (*)
                   → ModerationFlag (*)
                   → ChatEscalation (0..1)

All models use UUID PKs and TimeStampedModel inheritance.
Cloudinary handles image/video uploads via two-phase direct-upload.
"""
import uuid
import logging

from django.db import models, transaction
from cloudinary.models import CloudinaryField

from apps.common.models import TimeStampedModel
from apps.authentication.models import UnifiedUser

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# ENUMS
# ─────────────────────────────────────────────────────────────────────────────

class ConversationStatus(models.TextChoices):
    ACTIVE = "active", "Active"
    ARCHIVED = "archived", "Archived"
    BLOCKED = "blocked", "Blocked"
    ESCALATED = "escalated", "Escalated (Admin Review)"


class MessageType(models.TextChoices):
    TEXT = "text", "Text"
    IMAGE = "image", "Image"
    OFFER = "offer", "Price Offer"
    SYSTEM = "system", "System Notification"
    DELIVERY_CONFIRM = "delivery_confirm", "Delivery Confirmation"


class OfferStatus(models.TextChoices):
    PENDING = "pending", "Pending Buyer Response"
    ACCEPTED = "accepted", "Accepted"
    DECLINED = "declined", "Declined"
    EXPIRED = "expired", "Expired"
    CANCELLED = "cancelled", "Cancelled by Vendor"


class FlagReason(models.TextChoices):
    SPAM = "spam", "Spam"
    HARASSMENT = "harassment", "Harassment / Threats"
    FRAUD = "fraud", "Fraud Attempt"
    INAPPROPRIATE = "inappropriate", "Inappropriate Content"
    OTHER = "other", "Other"


class EscalationStatus(models.TextChoices):
    OPEN = "open", "Open"
    UNDER_REVIEW = "under_review", "Under Review"
    RESOLVED = "resolved", "Resolved"
    DISMISSED = "dismissed", "Dismissed"


# ─────────────────────────────────────────────────────────────────────────────
# CONVERSATION
# ─────────────────────────────────────────────────────────────────────────────

class Conversation(TimeStampedModel):
    """
    A messaging thread between one buyer and one vendor,
    optionally scoped to a specific product.

    Design decisions:
      - A buyer can open multiple conversations with the same vendor
        (e.g., different products) — no unique_together constraint.
      - Archiving is the soft-close mechanism; hard-delete is disallowed.
      - status transitions must be atomic.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    buyer = models.ForeignKey(
        UnifiedUser,
        on_delete=models.CASCADE,
        related_name="buyer_conversations",
    )
    vendor = models.ForeignKey(
        UnifiedUser,
        on_delete=models.CASCADE,
        related_name="vendor_conversations",
    )
    # Optional product scoping — NULL = general inquiry
    product_id = models.UUIDField(null=True, blank=True, db_index=True)
    product_title_snapshot = models.CharField(max_length=512, blank=True)

    status = models.CharField(
        max_length=20,
        choices=ConversationStatus.choices,
        default=ConversationStatus.ACTIVE,
        db_index=True,
    )

    # Derived fields updated via Message.save() signal / service
    last_message_at = models.DateTimeField(null=True, blank=True, db_index=True)
    unread_buyer_count = models.PositiveIntegerField(default=0)
    unread_vendor_count = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "chat_conversations"
        ordering = ["-last_message_at"]
        indexes = [
            models.Index(fields=["buyer", "status"]),
            models.Index(fields=["vendor", "status"]),
        ]

    def __str__(self) -> str:
        return f"Conv {self.id!s:.8} | {self.buyer_id} ↔ {self.vendor_id}"

    @transaction.atomic
    def archive(self) -> None:
        """Soft-close a conversation. Idempotent."""
        if self.status == ConversationStatus.ARCHIVED:
            return
        self.status = ConversationStatus.ARCHIVED
        self.save(update_fields=["status", "updated_at"])
        logger.info("Conversation archived: id=%s", self.id)

    @transaction.atomic
    def escalate(self) -> None:
        """Mark conversation for admin review."""
        self.status = ConversationStatus.ESCALATED
        self.save(update_fields=["status", "updated_at"])
        logger.info("Conversation escalated: id=%s", self.id)


# ─────────────────────────────────────────────────────────────────────────────
# MESSAGE
# ─────────────────────────────────────────────────────────────────────────────

class Message(TimeStampedModel):
    """
    A single message within a Conversation.
    Author is determined by FK — application enforces buyer/vendor restriction.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    conversation = models.ForeignKey(
        Conversation,
        on_delete=models.CASCADE,
        related_name="messages",
    )
    author = models.ForeignKey(
        UnifiedUser,
        on_delete=models.SET_NULL,
        null=True,
        related_name="chat_messages",
    )
    message_type = models.CharField(
        max_length=20,
        choices=MessageType.choices,
        default=MessageType.TEXT,
    )
    body = models.TextField(blank=True)
    is_read_by_buyer = models.BooleanField(default=False)
    is_read_by_vendor = models.BooleanField(default=False)
    is_deleted = models.BooleanField(default=False)

    class Meta:
        db_table = "chat_messages"
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["conversation", "created_at"]),
            models.Index(fields=["author", "is_read_by_buyer"]),
        ]

    def __str__(self) -> str:
        return f"Msg {self.id!s:.8} [{self.message_type}] in Conv {self.conversation_id!s:.8}"


# ─────────────────────────────────────────────────────────────────────────────
# MESSAGE MEDIA (Cloudinary two-phase upload)
# ─────────────────────────────────────────────────────────────────────────────

class MessageMedia(TimeStampedModel):
    """
    Cloudinary-hosted image/video attached to a Message.
    Upload flow: client presigns via /api/v1/common/cloudinary-presign/ →
    uploads directly to Cloudinary → sends public_id to backend → stored here.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    message = models.OneToOneField(
        Message,
        on_delete=models.CASCADE,
        related_name="media",
    )
    cloudinary_image = CloudinaryField(
        "chat_media",
        folder="fashionistar/chat",
        null=True,
        blank=True,
    )
    media_type = models.CharField(
        max_length=10,
        choices=[("image", "Image"), ("video", "Video")],
        default="image",
    )
    alt_text = models.CharField(max_length=255, blank=True)

    class Meta:
        db_table = "chat_message_media"

    def __str__(self) -> str:
        return f"Media for Msg {self.message_id!s:.8}"


# ─────────────────────────────────────────────────────────────────────────────
# CHAT OFFER (vendor → buyer price proposal)
# ─────────────────────────────────────────────────────────────────────────────

class ChatOffer(TimeStampedModel):
    """
    A price offer sent by a vendor to a buyer within a conversation.
    Accepting the offer creates an order via the order service.
    Status machine: PENDING → ACCEPTED | DECLINED | EXPIRED | CANCELLED
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    conversation = models.ForeignKey(
        Conversation,
        on_delete=models.CASCADE,
        related_name="offers",
    )
    message = models.OneToOneField(
        Message,
        on_delete=models.CASCADE,
        related_name="offer",
        null=True,
        blank=True,
    )
    product_id = models.UUIDField()
    product_title_snapshot = models.CharField(max_length=512)
    quantity = models.PositiveIntegerField(default=1)
    offered_price = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default="NGN")
    status = models.CharField(
        max_length=20,
        choices=OfferStatus.choices,
        default=OfferStatus.PENDING,
        db_index=True,
    )
    expires_at = models.DateTimeField(null=True, blank=True)
    responded_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        db_table = "chat_offers"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Offer {self.id!s:.8} | ₦{self.offered_price} [{self.status}]"

    @transaction.atomic
    def accept(self, accepted_by: "UnifiedUser") -> None:
        """
        Accept this offer. Creates a checkout-ready entry.
        Idempotent — raises ValueError if already in terminal state.
        """
        if self.status != OfferStatus.PENDING:
            raise ValueError(f"Cannot accept offer in status '{self.status}'")
        from django.utils import timezone
        self.status = OfferStatus.ACCEPTED
        self.responded_at = timezone.now()
        self.save(update_fields=["status", "responded_at", "updated_at"])
        logger.info(
            "ChatOffer accepted: id=%s buyer=%s", self.id, accepted_by.id
        )

    @transaction.atomic
    def decline(self, declined_by: "UnifiedUser") -> None:
        """Decline this offer. Idempotent."""
        if self.status != OfferStatus.PENDING:
            raise ValueError(f"Cannot decline offer in status '{self.status}'")
        from django.utils import timezone
        self.status = OfferStatus.DECLINED
        self.responded_at = timezone.now()
        self.save(update_fields=["status", "responded_at", "updated_at"])
        logger.info("ChatOffer declined: id=%s", self.id)


# ─────────────────────────────────────────────────────────────────────────────
# MODERATION FLAG
# ─────────────────────────────────────────────────────────────────────────────

class ModerationFlag(TimeStampedModel):
    """
    A moderation report filed by either party in a conversation.
    Triggers admin review workflow (ChatEscalation).
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    conversation = models.ForeignKey(
        Conversation,
        on_delete=models.CASCADE,
        related_name="flags",
    )
    reported_by = models.ForeignKey(
        UnifiedUser,
        on_delete=models.SET_NULL,
        null=True,
        related_name="filed_flags",
    )
    reason = models.CharField(max_length=20, choices=FlagReason.choices)
    details = models.TextField(blank=True)
    is_reviewed = models.BooleanField(default=False)
    reviewed_by = models.ForeignKey(
        UnifiedUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_flags",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "chat_moderation_flags"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Flag {self.id!s:.8} [{self.reason}] on Conv {self.conversation_id!s:.8}"


# ─────────────────────────────────────────────────────────────────────────────
# CHAT ESCALATION
# ─────────────────────────────────────────────────────────────────────────────

class ChatEscalation(TimeStampedModel):
    """
    Admin takeover record for an escalated conversation.
    One-to-one per conversation — only one active escalation allowed.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    conversation = models.OneToOneField(
        Conversation,
        on_delete=models.CASCADE,
        related_name="escalation",
    )
    flag = models.ForeignKey(
        ModerationFlag,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="escalation",
    )
    assigned_admin = models.ForeignKey(
        UnifiedUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_escalations",
    )
    status = models.CharField(
        max_length=20,
        choices=EscalationStatus.choices,
        default=EscalationStatus.OPEN,
        db_index=True,
    )
    resolution_notes = models.TextField(blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "chat_escalations"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Escalation {self.id!s:.8} [{self.status}] on Conv {self.conversation_id!s:.8}"
