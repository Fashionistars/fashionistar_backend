# apps/support/admin.py
"""Django admin registration for the Support domain."""

from django.contrib import admin

from apps.support.models import SupportTicket, TicketMessage, TicketEscalation


class TicketMessageInline(admin.TabularInline):
    model       = TicketMessage
    extra       = 0
    fields      = ["author", "body", "is_staff_reply", "created_at"]
    readonly_fields = ["created_at"]
    show_change_link = False


@admin.register(SupportTicket)
class SupportTicketAdmin(admin.ModelAdmin):
    list_display   = ["id", "submitter", "category", "priority", "status", "title", "assigned_to", "created_at"]
    list_filter    = ["status", "priority", "category"]
    search_fields  = ["title", "description", "submitter__email"]
    readonly_fields = ["id", "created_at", "updated_at", "resolved_at", "closed_at"]
    raw_id_fields  = ["submitter", "assigned_to"]
    inlines        = [TicketMessageInline]
    ordering       = ["-created_at"]


@admin.register(TicketMessage)
class TicketMessageAdmin(admin.ModelAdmin):
    list_display  = ["id", "ticket", "author", "is_staff_reply", "created_at"]
    list_filter   = ["is_staff_reply"]
    search_fields = ["body", "author__email"]
    readonly_fields = ["id", "created_at"]


@admin.register(TicketEscalation)
class TicketEscalationAdmin(admin.ModelAdmin):
    list_display  = ["id", "ticket", "status", "escalated_by", "assigned_admin", "created_at"]
    list_filter   = ["status"]
    search_fields = ["reason", "resolution_notes"]
    readonly_fields = ["id", "created_at", "updated_at"]
