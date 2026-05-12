# apps/notification/admin.py
"""
Django Admin registration for the Notification domain.
"""
from django.contrib import admin
from django.utils.html import format_html

from apps.notification.models import (
    Notification,
    NotificationTemplate,
    NotificationPreference,
)


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display  = ("id", "recipient", "notification_type", "channel", "is_read_display", "created_at")
    list_filter   = ("notification_type", "channel", "failed")
    search_fields = ("recipient__email", "title")
    readonly_fields = (
        "recipient", "notification_type", "channel",
        "title", "body", "metadata",
        "sent_at", "read_at", "external_id",
        "retry_count", "failed", "error_msg",
        "created_at", "updated_at",
    )
    ordering = ("-created_at",)
    date_hierarchy = "created_at"

    @admin.display(description="Read?", boolean=True)
    def is_read_display(self, obj):
        return obj.is_read


@admin.register(NotificationTemplate)
class NotificationTemplateAdmin(admin.ModelAdmin):
    list_display  = ("notification_type", "channel", "is_active", "updated_at")
    list_filter   = ("channel", "is_active")
    search_fields = ("notification_type", "title_template")


@admin.register(NotificationPreference)
class NotificationPreferenceAdmin(admin.ModelAdmin):
    list_display  = ("user", "notification_type", "channel", "enabled")
    list_filter   = ("channel", "enabled")
    search_fields = ("user__email",)
