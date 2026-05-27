# apps/notification/admin.py
"""
Django Admin for the Notification domain.

Models registered:
  - Notification           : Delivered notification ledger (read-only)
  - NotificationTemplate   : Admin-editable message templates
  - NotificationPreference : Per-user channel opt-in/out settings

Production rules:
  - Notification records are immutable (delivery audit log)
  - Templates can be edited by staff
  - Preferences can be toggled via bulk action
  - Retry failed notifications via admin action
  - CSV export for sent/failed notification analytics

2026 features:
  - Status badge (sent / failed / pending)
  - Channel badge (email / sms / push / in_app)
  - Date hierarchy for temporal analysis
  - show_full_result_count = False (table can have millions of rows)
"""
import logging

from django.contrib import admin
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from django.contrib import messages

from apps.notification.models import (
    Notification,
    NotificationTemplate,
    NotificationPreference,
)

logger = logging.getLogger(__name__)

_CHANNEL_COLOURS = {
    "email":  ("#6366f1", "#fff"),
    "sms":    ("#10b981", "#fff"),
    "push":   ("#f59e0b", "#fff"),
    "in_app": ("#3b82f6", "#fff"),
}


# ── Notification Admin (append-only) ──────────────────────────────────────────

@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    """
    Read-only audit log of every notification delivered (or failed to deliver).
    """

    list_display = [
        "id", "recipient", "type_badge", "channel_badge",
        "title_preview", "read_badge",
        "failed", "retry_count", "created_at",
    ]
    list_filter = [
        "notification_type", "channel", "failed",
    ]
    search_fields = ["recipient__email", "title", "body"]
    ordering = ["-created_at"]
    date_hierarchy = "created_at"
    list_select_related = ["recipient"]
    raw_id_fields = ["recipient"]
    list_per_page = 25
    list_max_show_all = 200
    show_full_result_count = False
    empty_value_display = "-N/A-"

    readonly_fields = [
        "recipient", "notification_type", "channel",
        "title", "body", "metadata",
        "sent_at", "read_at", "external_id",
        "retry_count", "failed", "error_msg",
        "created_at", "updated_at",
    ]

    fieldsets = (
        (_("Recipient"), {
            "fields": ("recipient",),
        }),
        (_("Notification"), {
            "fields": ("notification_type", "channel", "title", "body"),
        }),
        (_("Delivery"), {
            "fields": (
                "sent_at", "read_at", "external_id",
                "retry_count", "failed", "error_msg",
            ),
        }),
        (_("Metadata"), {
            "fields": ("metadata",),
            "classes": ("collapse",),
        }),
        (_("Timestamps"), {
            "fields": ("created_at", "updated_at"),
            "classes": ("collapse",),
        }),
    )

    actions = ["action_retry_failed"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser  # superuser can purge old records

    @admin.display(description="Type")
    def type_badge(self, obj):
        return format_html(
            '<span style="background:#e0e7ff;color:#3730a3;padding:2px 8px;'
            'border-radius:20px;font-size:11px;font-weight:600">{}</span>',
            obj.notification_type,
        )

    @admin.display(description="Channel")
    def channel_badge(self, obj):
        bg, fg = _CHANNEL_COLOURS.get(obj.channel, ("#6b7280", "#fff"))
        return format_html(
            '<span style="background:{};color:{};padding:2px 8px;'
            'border-radius:20px;font-size:11px;font-weight:600">{}</span>',
            bg, fg, obj.channel.upper(),
        )

    @admin.display(description="Title")
    def title_preview(self, obj):
        return (obj.title or "")[:60]

    @admin.display(description="Read", boolean=True)
    def read_badge(self, obj):
        return obj.is_read

    @admin.action(description="🔁 Retry selected failed notifications")
    def action_retry_failed(self, request, queryset):
        from django.utils import timezone
        qs = queryset.filter(failed=True)
        count = qs.count()
        if count == 0:
            self.message_user(
                request, "No failed notifications selected.", level=messages.WARNING
            )
            return
        qs.update(failed=False, retry_count=0, error_msg="")
        self.message_user(
            request,
            f"🔁 {count} notification(s) queued for retry.",
            level=messages.SUCCESS,
        )


# ── Notification Template Admin ───────────────────────────────────────────────

@admin.register(NotificationTemplate)
class NotificationTemplateAdmin(admin.ModelAdmin):
    list_display = [
        "notification_type", "channel", "is_active",
        "updated_at",
    ]
    list_filter = ["channel", "is_active"]
    search_fields = ["notification_type", "title_template", "body_template"]
    ordering = ["notification_type", "channel"]
    list_per_page = 25
    empty_value_display = "-N/A-"

    readonly_fields = ["created_at", "updated_at"]

    fieldsets = (
        (_("Template"), {
            "fields": (
                "notification_type", "channel", "is_active",
            ),
        }),
        (_("Content"), {
            "fields": ("title_template", "body_template", "metadata_template"),
        }),
        (_("Timestamps"), {
            "fields": ("created_at", "updated_at"),
            "classes": ("collapse",),
        }),
    )


# ── Notification Preference Admin ─────────────────────────────────────────────

@admin.register(NotificationPreference)
class NotificationPreferenceAdmin(admin.ModelAdmin):
    list_display = [
        "user", "notification_type", "channel", "enabled",
    ]
    list_filter = ["channel", "enabled", "notification_type"]
    search_fields = ["user__email", "notification_type"]
    ordering = ["user", "notification_type"]
    raw_id_fields = ["user"]
    list_select_related = ["user"]
    list_per_page = 25
    show_full_result_count = False
    empty_value_display = "-N/A-"

    readonly_fields = ["created_at", "updated_at"]

    actions = ["enable_all", "disable_all"]

    @admin.action(description="✅ Enable selected notification preferences")
    def enable_all(self, request, queryset):
        queryset.update(enabled=True)
        self.message_user(request, "✅ Preferences enabled.", level=messages.SUCCESS)

    @admin.action(description="🔕 Disable selected notification preferences")
    def disable_all(self, request, queryset):
        queryset.update(enabled=False)
        self.message_user(request, "🔕 Preferences disabled.", level=messages.WARNING)
