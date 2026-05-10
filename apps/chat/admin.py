"""
apps/chat/admin.py — Jazzmin-compatible Django admin for Chat domain.
"""
from django.contrib import admin
from apps.chat.models import (
    Conversation,
    Message,
    MessageMedia,
    ChatOffer,
    ModerationFlag,
    ChatEscalation,
)


class MessageInline(admin.TabularInline):
    model = Message
    fields = ["author", "message_type", "body", "is_read_by_buyer", "is_read_by_vendor", "created_at"]
    readonly_fields = ["created_at"]
    extra = 0
    can_delete = False
    show_change_link = True


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = [
        "id", "buyer", "vendor", "status", "product_title_snapshot",
        "unread_buyer_count", "unread_vendor_count", "last_message_at",
    ]
    list_filter = ["status"]
    search_fields = ["buyer__email", "vendor__email", "product_title_snapshot"]
    readonly_fields = ["id", "last_message_at", "created_at", "updated_at"]
    inlines = [MessageInline]


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ["id", "conversation", "author", "message_type", "body_preview", "created_at"]
    list_filter = ["message_type", "is_deleted"]
    search_fields = ["author__email", "body"]
    readonly_fields = ["id", "created_at", "updated_at"]

    def body_preview(self, obj):
        return (obj.body or "")[:60]
    body_preview.short_description = "Body"


@admin.register(ChatOffer)
class ChatOfferAdmin(admin.ModelAdmin):
    list_display = [
        "id", "conversation", "product_title_snapshot",
        "offered_price", "currency", "status", "created_at",
    ]
    list_filter = ["status", "currency"]
    readonly_fields = ["id", "created_at", "updated_at", "responded_at"]


@admin.register(ModerationFlag)
class ModerationFlagAdmin(admin.ModelAdmin):
    list_display = ["id", "conversation", "reported_by", "reason", "is_reviewed", "created_at"]
    list_filter = ["reason", "is_reviewed"]
    readonly_fields = ["id", "created_at", "updated_at"]


@admin.register(ChatEscalation)
class ChatEscalationAdmin(admin.ModelAdmin):
    list_display = ["id", "conversation", "assigned_admin", "status", "resolved_at", "created_at"]
    list_filter = ["status"]
    readonly_fields = ["id", "created_at", "updated_at"]
