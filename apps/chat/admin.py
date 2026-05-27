# apps/chat/admin.py
"""
Django Admin for the Chat domain.

Models registered:
  - Conversation    : Buyer ↔ Vendor conversation threads
  - Message         : Individual messages (append-only audit view)
  - MessageMedia    : Media attachments (read-only)
  - ChatOffer       : Price/offer negotiations inside a conversation
  - ModerationFlag  : User-reported content (moderation queue)
  - ChatEscalation  : Escalated conversations needing admin attention

Production rules:
  - Message records are effectively immutable (soft-delete only via is_deleted)
  - Offer amounts are read-only (financial record)
  - ModerationFlag review action gated to staff
  - Escalation assignment action available

2026 features:
  - Unread count badges in Conversation list
  - Message body preview truncated to 80 chars
  - Offer status colour badge
  - Moderation quick-review bulk action
  - date_hierarchy on all time-series admins
  - show_full_result_count = False (chat tables grow fast)
"""
import logging

from django.contrib import admin
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from django.contrib import messages

from apps.chat.models import (
    Conversation,
    Message,
    MessageMedia,
    ChatOffer,
    ModerationFlag,
    ChatEscalation,
)

logger = logging.getLogger(__name__)


# ── Inlines ───────────────────────────────────────────────────────────────────

class MessageInline(admin.TabularInline):
    """Read-only inline showing the last N messages in a conversation."""
    model = Message
    fields = [
        "author", "message_type", "body_preview_inline",
        "is_read_by_buyer", "is_read_by_vendor", "is_deleted", "created_at",
    ]
    readonly_fields = [
        "author", "message_type", "body_preview_inline",
        "is_read_by_buyer", "is_read_by_vendor", "is_deleted", "created_at",
    ]
    extra = 0
    can_delete = False
    max_num = 20
    show_change_link = True
    ordering = ["-created_at"]

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    @admin.display(description="Body")
    def body_preview_inline(self, obj):
        return (obj.body or "")[:80] + ("…" if len(obj.body or "") > 80 else "")


class ChatOfferInline(admin.TabularInline):
    """Read-only offer summary inline inside a conversation."""
    model = ChatOffer
    fields = [
        "product_title_snapshot", "offered_price", "currency",
        "status", "responded_at",
    ]
    readonly_fields = [
        "product_title_snapshot", "offered_price", "currency",
        "status", "responded_at",
    ]
    extra = 0
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False


# ── Conversation Admin ────────────────────────────────────────────────────────

@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = [
        "id", "buyer", "vendor", "status_badge",
        "product_title_snapshot",
        "unread_buyer_count", "unread_vendor_count",
        "last_message_at",
    ]
    list_filter = ["status"]
    search_fields = [
        "buyer__email", "vendor__email", "product_title_snapshot",
    ]
    ordering = ["-last_message_at"]
    date_hierarchy = "last_message_at"
    list_select_related = ["buyer", "vendor"]
    raw_id_fields = ["buyer", "vendor"]
    list_per_page = 25
    list_max_show_all = 200
    show_full_result_count = False
    empty_value_display = "-N/A-"

    readonly_fields = ["id", "last_message_at", "created_at", "updated_at"]

    fieldsets = (
        (_("Parties"), {
            "fields": ("buyer", "vendor"),
        }),
        (_("Context"), {
            "fields": ("product_title_snapshot", "product_snapshot_id", "status"),
        }),
        (_("Read Counts"), {
            "fields": ("unread_buyer_count", "unread_vendor_count"),
        }),
        (_("Timestamps"), {
            "fields": ("last_message_at", "created_at", "updated_at"),
            "classes": ("collapse",),
        }),
    )

    inlines = [MessageInline, ChatOfferInline]

    @admin.display(description="Status")
    def status_badge(self, obj):
        colours = {
            "active":    ("#10b981", "#fff"),
            "closed":    ("#6b7280", "#fff"),
            "blocked":   ("#ef4444", "#fff"),
            "archived":  ("#94a3b8", "#fff"),
        }
        bg, fg = colours.get(obj.status, ("#6b7280", "#fff"))
        return format_html(
            '<span style="background:{};color:{};padding:2px 8px;'
            'border-radius:20px;font-size:11px;font-weight:600">{}</span>',
            bg, fg, obj.status.upper(),
        )


# ── Message Admin ─────────────────────────────────────────────────────────────

@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = [
        "id", "conversation", "author", "message_type_badge",
        "body_preview", "is_deleted", "created_at",
    ]
    list_filter = ["message_type", "is_deleted"]
    search_fields = ["author__email", "body"]
    ordering = ["-created_at"]
    date_hierarchy = "created_at"
    list_select_related = ["conversation", "author"]
    raw_id_fields = ["conversation", "author"]
    list_per_page = 25
    list_max_show_all = 200
    show_full_result_count = False
    empty_value_display = "-N/A-"

    readonly_fields = ["id", "created_at", "updated_at"]

    fieldsets = (
        (_("Message"), {
            "fields": (
                "conversation", "author", "message_type",
                "body", "is_deleted",
            ),
        }),
        (_("Read Status"), {
            "fields": ("is_read_by_buyer", "is_read_by_vendor"),
        }),
        (_("Timestamps"), {
            "fields": ("created_at", "updated_at"),
            "classes": ("collapse",),
        }),
    )

    @admin.display(description="Body")
    def body_preview(self, obj):
        return (obj.body or "")[:80] + ("…" if len(obj.body or "") > 80 else "")

    @admin.display(description="Type")
    def message_type_badge(self, obj):
        colours = {
            "text":   ("#6366f1", "#fff"),
            "image":  ("#10b981", "#fff"),
            "offer":  ("#f59e0b", "#fff"),
            "file":   ("#3b82f6", "#fff"),
            "system": ("#94a3b8", "#fff"),
        }
        bg, fg = colours.get(obj.message_type, ("#6b7280", "#fff"))
        return format_html(
            '<span style="background:{};color:{};padding:2px 7px;'
            'border-radius:20px;font-size:11px;font-weight:600">{}</span>',
            bg, fg, obj.message_type.upper(),
        )


# ── Message Media Admin ───────────────────────────────────────────────────────

@admin.register(MessageMedia)
class MessageMediaAdmin(admin.ModelAdmin):
    list_display = ["id", "message", "media_type", "thumbnail_preview", "created_at"]
    list_filter = ["media_type"]
    search_fields = ["message__id", "cloudinary_url"]
    ordering = ["-created_at"]
    date_hierarchy = "created_at"
    list_select_related = ["message"]
    list_per_page = 25
    show_full_result_count = False
    empty_value_display = "-N/A-"

    readonly_fields = [
        f.name for f in MessageMedia._meta.get_fields()
        if hasattr(f, "name")
    ]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    @admin.display(description="Preview")
    def thumbnail_preview(self, obj):
        url = getattr(obj, "cloudinary_url", None)
        if url and obj.media_type in ("image",):
            return format_html(
                '<img src="{}" height="40" style="border-radius:4px;'
                'object-fit:cover;border:1px solid #e2e8f0;" />',
                url,
            )
        return "—"


# ── Chat Offer Admin ──────────────────────────────────────────────────────────

@admin.register(ChatOffer)
class ChatOfferAdmin(admin.ModelAdmin):
    list_display = [
        "id", "conversation", "product_title_snapshot",
        "offered_price_display", "currency", "status_badge", "created_at",
    ]
    list_filter = ["status", "currency"]
    search_fields = [
        "conversation__buyer__email",
        "conversation__vendor__email",
        "product_title_snapshot",
    ]
    ordering = ["-created_at"]
    date_hierarchy = "created_at"
    list_select_related = ["conversation"]
    list_per_page = 25
    show_full_result_count = False
    empty_value_display = "-N/A-"

    readonly_fields = [
        "id", "offered_price", "currency", "created_at",
        "updated_at", "responded_at",
    ]

    fieldsets = (
        (_("Offer"), {
            "fields": (
                "conversation", "product_title_snapshot",
                "offered_price", "currency", "status",
            ),
        }),
        (_("Product Snapshot"), {
            "fields": ("product_snapshot_id",),
            "classes": ("collapse",),
        }),
        (_("Timeline"), {
            "fields": ("responded_at", "created_at", "updated_at"),
            "classes": ("collapse",),
        }),
    )

    @admin.display(description="Status")
    def status_badge(self, obj):
        colours = {
            "pending":  ("#f59e0b", "#fff"),
            "accepted": ("#10b981", "#fff"),
            "rejected": ("#ef4444", "#fff"),
            "expired":  ("#94a3b8", "#fff"),
        }
        bg, fg = colours.get(obj.status, ("#6b7280", "#fff"))
        return format_html(
            '<span style="background:{};color:{};padding:2px 8px;'
            'border-radius:20px;font-size:11px;font-weight:600">{}</span>',
            bg, fg, obj.status.upper(),
        )

    @admin.display(description="Amount")
    def offered_price_display(self, obj):
        return format_html(
            '<strong>₦{:,.2f}</strong>', obj.offered_price
        )


# ── Moderation Flag Admin ─────────────────────────────────────────────────────

@admin.register(ModerationFlag)
class ModerationFlagAdmin(admin.ModelAdmin):
    list_display = [
        "id", "conversation", "reported_by",
        "reason", "reviewed_badge", "created_at",
    ]
    list_filter = ["reason", "is_reviewed"]
    search_fields = [
        "conversation__buyer__email",
        "reported_by__email",
        "notes",
    ]
    ordering = ["is_reviewed", "-created_at"]
    date_hierarchy = "created_at"
    list_select_related = ["conversation", "reported_by", "reviewed_by"]
    raw_id_fields = ["conversation", "reported_by"]
    list_per_page = 25
    show_full_result_count = False
    empty_value_display = "-N/A-"

    readonly_fields = ["id", "created_at", "updated_at", "reviewed_at"]

    fieldsets = (
        (_("Flag"), {
            "fields": (
                "conversation", "reported_by", "reason", "notes",
            ),
        }),
        (_("Review"), {
            "fields": (
                "is_reviewed", "reviewed_by",
                "review_action", "reviewed_at",
            ),
        }),
        (_("Timestamps"), {
            "fields": ("created_at", "updated_at"),
            "classes": ("collapse",),
        }),
    )

    actions = ["action_mark_reviewed"]

    @admin.display(description="Reviewed", boolean=True)
    def reviewed_badge(self, obj):
        return obj.is_reviewed

    @admin.action(description="✅ Mark selected flags as reviewed")
    def action_mark_reviewed(self, request, queryset):
        from django.utils import timezone
        updated = queryset.filter(is_reviewed=False).update(
            is_reviewed=True,
            reviewed_by=request.user,
            reviewed_at=timezone.now(),
        )
        self.message_user(
            request,
            f"✅ {updated} flag(s) marked as reviewed.",
            level=messages.SUCCESS,
        )


# ── Chat Escalation Admin ─────────────────────────────────────────────────────

@admin.register(ChatEscalation)
class ChatEscalationAdmin(admin.ModelAdmin):
    list_display = [
        "id", "conversation", "assigned_admin",
        "status_badge", "resolved_at", "created_at",
    ]
    list_filter = ["status"]
    search_fields = [
        "conversation__buyer__email",
        "assigned_admin__email",
        "reason",
    ]
    ordering = ["status", "-created_at"]
    date_hierarchy = "created_at"
    list_select_related = ["conversation", "assigned_admin"]
    raw_id_fields = ["conversation", "assigned_admin"]
    list_per_page = 25
    show_full_result_count = False
    empty_value_display = "-N/A-"

    readonly_fields = ["id", "created_at", "updated_at", "resolved_at"]

    fieldsets = (
        (_("Escalation"), {
            "fields": (
                "conversation", "reason",
                "assigned_admin", "status",
            ),
        }),
        (_("Resolution"), {
            "fields": ("resolution_notes", "resolved_at"),
        }),
        (_("Timestamps"), {
            "fields": ("created_at", "updated_at"),
            "classes": ("collapse",),
        }),
    )

    actions = ["action_resolve"]

    @admin.display(description="Status")
    def status_badge(self, obj):
        colours = {
            "open":     ("#f59e0b", "#fff"),
            "resolved": ("#10b981", "#fff"),
            "closed":   ("#6b7280", "#fff"),
        }
        bg, fg = colours.get(obj.status, ("#6b7280", "#fff"))
        return format_html(
            '<span style="background:{};color:{};padding:2px 8px;'
            'border-radius:20px;font-size:11px;font-weight:600">{}</span>',
            bg, fg, obj.status.upper(),
        )

    @admin.action(description="✅ Mark selected escalations as Resolved")
    def action_resolve(self, request, queryset):
        if not request.user.is_staff:
            self.message_user(request, "Staff only.", level=messages.ERROR)
            return
        from django.utils import timezone
        updated = queryset.exclude(status="resolved").update(
            status="resolved",
            resolved_at=timezone.now(),
        )
        self.message_user(
            request,
            f"✅ {updated} escalation(s) resolved.",
            level=messages.SUCCESS,
        )
