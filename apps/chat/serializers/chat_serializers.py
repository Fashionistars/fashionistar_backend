"""
apps/chat/serializers/chat_serializers.py
DRF serializers for the Chat domain.
"""
from rest_framework import serializers
from apps.chat.models import (
    Conversation,
    Message,
    MessageMedia,
    ChatOffer,
    ModerationFlag,
    ChatEscalation,
)


# ─────────────────────────────────────────────────────────────────────────────
# PARTICIPANT REFS
# ─────────────────────────────────────────────────────────────────────────────

class ParticipantSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    full_name = serializers.SerializerMethodField()
    avatar_url = serializers.SerializerMethodField()

    def get_full_name(self, obj):
        return obj.get_full_name() or obj.email

    def get_avatar_url(self, obj):
        return getattr(obj, "avatar_url", None)


# ─────────────────────────────────────────────────────────────────────────────
# MESSAGE MEDIA
# ─────────────────────────────────────────────────────────────────────────────

class MessageMediaSerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = MessageMedia
        fields = ["id", "image_url", "media_type", "alt_text"]

    def get_image_url(self, obj):
        return obj.cloudinary_image.url if obj.cloudinary_image else None


# ─────────────────────────────────────────────────────────────────────────────
# OFFER
# ─────────────────────────────────────────────────────────────────────────────

class ChatOfferSerializer(serializers.ModelSerializer):
    class Meta:
        model = ChatOffer
        fields = [
            "id",
            "product_id",
            "product_title_snapshot",
            "quantity",
            "offered_price",
            "currency",
            "status",
            "expires_at",
            "responded_at",
            "notes",
            "created_at",
        ]
        read_only_fields = ["id", "status", "responded_at", "created_at"]


# ─────────────────────────────────────────────────────────────────────────────
# MESSAGE
# ─────────────────────────────────────────────────────────────────────────────

class MessageSerializer(serializers.ModelSerializer):
    author_id = serializers.UUIDField(source="author.id", read_only=True)
    author_name = serializers.SerializerMethodField()
    media = MessageMediaSerializer(read_only=True)
    offer = ChatOfferSerializer(read_only=True)

    class Meta:
        model = Message
        fields = [
            "id",
            "message_type",
            "body",
            "author_id",
            "author_name",
            "is_read_by_buyer",
            "is_read_by_vendor",
            "is_deleted",
            "media",
            "offer",
            "created_at",
        ]

    def get_author_name(self, obj):
        if obj.author:
            return obj.author.get_full_name() or obj.author.email
        return "Deleted User"


class SendMessageSerializer(serializers.Serializer):
    body = serializers.CharField(min_length=1, max_length=4000)
    message_type = serializers.ChoiceField(
        choices=["text", "image"],
        default="text",
    )


# ─────────────────────────────────────────────────────────────────────────────
# CONVERSATION
# ─────────────────────────────────────────────────────────────────────────────

class ConversationListSerializer(serializers.ModelSerializer):
    other_party_name = serializers.SerializerMethodField()
    other_party_id = serializers.SerializerMethodField()
    last_message_preview = serializers.SerializerMethodField()
    unread_count = serializers.SerializerMethodField()

    class Meta:
        model = Conversation
        fields = [
            "id",
            "product_id",
            "product_title_snapshot",
            "status",
            "other_party_id",
            "other_party_name",
            "last_message_at",
            "unread_count",
            "last_message_preview",
        ]

    def get_other_party_name(self, obj):
        request = self.context.get("request")
        if not request:
            return None
        if request.user.id == obj.buyer_id:
            return obj.vendor.get_full_name() or obj.vendor.email
        return obj.buyer.get_full_name() or obj.buyer.email

    def get_other_party_id(self, obj):
        request = self.context.get("request")
        if not request:
            return None
        if request.user.id == obj.buyer_id:
            return str(obj.vendor_id)
        return str(obj.buyer_id)

    def get_last_message_preview(self, obj):
        last = obj.messages.filter(is_deleted=False).last()
        if last:
            return last.body[:80]
        return ""

    def get_unread_count(self, obj):
        request = self.context.get("request")
        if not request:
            return 0
        if request.user.id == obj.buyer_id:
            return obj.unread_buyer_count
        return obj.unread_vendor_count


class StartConversationSerializer(serializers.Serializer):
    vendor_id = serializers.UUIDField()
    product_id = serializers.UUIDField(required=False, allow_null=True)
    product_title_snapshot = serializers.CharField(
        max_length=512, required=False, default=""
    )
    initial_message = serializers.CharField(
        min_length=1, max_length=4000, required=False, default=""
    )


class CreateOfferSerializer(serializers.Serializer):
    product_id = serializers.UUIDField()
    product_title_snapshot = serializers.CharField(max_length=512)
    quantity = serializers.IntegerField(min_value=1, default=1)
    offered_price = serializers.DecimalField(max_digits=12, decimal_places=2)
    notes = serializers.CharField(max_length=1000, required=False, default="")


class FlagConversationSerializer(serializers.Serializer):
    reason = serializers.ChoiceField(
        choices=["spam", "harassment", "fraud", "inappropriate", "other"]
    )
    details = serializers.CharField(max_length=2000, required=False, default="")
