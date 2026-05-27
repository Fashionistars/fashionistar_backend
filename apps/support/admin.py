# apps/support/admin.py
"""
Django Admin for the Support domain.

Models registered:
  - SupportTicket    : Customer support tickets with priority/status management
  - TicketMessage    : Conversation thread within a ticket (mostly read-only)
  - TicketEscalation : Escalations to senior admin/compliance

Production rules:
  - Tickets are append-only audit-style records; status transitions via actions
  - Messages cannot be edited after creation (is_deleted flag for soft-purge)
  - Escalation assignment is superuser-only action
  - Bulk actions: Close Tickets, Escalate Tickets, Resolve Selected

2026 features:
  - Priority badge (Critical → Low) with colour coding
  - Status badge with full colour range
  - Date hierarchy for temporal analysis
  - show_full_result_count = False
  - Response time indicator (if resolved_at exists)
  - Staff assignment dropdown via raw_id_fields
"""
import logging

from django.contrib import admin
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from django.contrib import messages
from django.utils import timezone

from apps.support.models import SupportTicket, TicketMessage, TicketEscalation

logger = logging.getLogger(__name__)

# ── Priority colours ──────────────────────────────────────────────────────────
_PRIORITY_COLOURS = {
    "critical": ("#dc2626", "#fff"),
    "high":     ("#ef4444", "#fff"),
    "medium":   ("#f59e0b", "#fff"),
    "low":      ("#10b981", "#fff"),
}

# ── Status colours ────────────────────────────────────────────────────────────
_STATUS_COLOURS = {
    "open":        ("#3b82f6", "#fff"),
    "in_progress": ("#8b5cf6", "#fff"),
    "resolved":    ("#10b981", "#fff"),
    "closed":      ("#6b7280", "#fff"),
    "escalated":   ("#dc2626", "#fff"),
    "pending":     ("#f59e0b", "#fff"),
}


# ── Inlines ───────────────────────────────────────────────────────────────────

class TicketMessageInline(admin.TabularInline):
    """Chronological message thread inside a ticket (read-only)."""
    model = TicketMessage
    fields = ["author", "body_preview", "is_staff_reply", "created_at"]
    readonly_fields = ["author", "body_preview", "is_staff_reply", "created_at"]
    extra = 0
    can_delete = False
    ordering = ["created_at"]
    max_num = 50

    def has_add_permission(self, request, obj=None):
        # Staff can reply via the normal API; not from admin to avoid confusion
        return False

    def has_change_permission(self, request, obj=None):
        return False

    @admin.display(description="Message")
    def body_preview(self, obj):
        return (obj.body or "")[:100] + ("…" if len(obj.body or "") > 100 else "")


# ── Support Ticket Admin ──────────────────────────────────────────────────────

@admin.register(SupportTicket)
class SupportTicketAdmin(admin.ModelAdmin):
    list_display = [
        "id", "submitter", "priority_badge", "status_badge",
        "category", "title_preview", "assigned_to",
        "response_time", "created_at",
    ]
    list_filter = [
        "status", "priority", "category",
    ]
    search_fields = [
        "title", "description", "submitter__email", "id",
    ]
    ordering = ["-created_at"]
    date_hierarchy = "created_at"
    list_select_related = ["submitter", "assigned_to"]
    raw_id_fields = ["submitter", "assigned_to"]
    list_per_page = 25
    list_max_show_all = 200
    show_full_result_count = False
    empty_value_display = "-N/A-"

    readonly_fields = [
        "id", "created_at", "updated_at",
        "resolved_at", "closed_at",
    ]

    fieldsets = (
        (_("Ticket"), {
            "fields": (
                "id", "submitter", "category",
                "priority", "status", "title",
            ),
        }),
        (_("Description"), {
            "fields": ("description",),
        }),
        (_("Assignment"), {
            "fields": ("assigned_to", "internal_notes"),
        }),
        (_("Resolution"), {
            "fields": ("resolution_summary", "resolved_at", "closed_at"),
        }),
        (_("Timestamps"), {
            "fields": ("created_at", "updated_at"),
            "classes": ("collapse",),
        }),
    )

    inlines = [TicketMessageInline]

    actions = [
        "action_close_tickets",
        "action_resolve_tickets",
        "action_escalate_tickets",
        "action_assign_to_me",
    ]

    # ── List display helpers ─────────────────────────────────────────────────

    @admin.display(description="Priority")
    def priority_badge(self, obj):
        bg, fg = _PRIORITY_COLOURS.get(obj.priority, ("#6b7280", "#fff"))
        return format_html(
            '<span style="background:{};color:{};padding:2px 8px;'
            'border-radius:20px;font-size:11px;font-weight:700">{}</span>',
            bg, fg, obj.priority.upper(),
        )

    @admin.display(description="Status")
    def status_badge(self, obj):
        bg, fg = _STATUS_COLOURS.get(obj.status, ("#6b7280", "#fff"))
        label = obj.get_status_display() if hasattr(obj, "get_status_display") else obj.status
        return format_html(
            '<span style="background:{};color:{};padding:2px 8px;'
            'border-radius:20px;font-size:11px;font-weight:600">{}</span>',
            bg, fg, label,
        )

    @admin.display(description="Title")
    def title_preview(self, obj):
        return (obj.title or "")[:60]

    @admin.display(description="Response Time")
    def response_time(self, obj):
        if obj.resolved_at and obj.created_at:
            delta = obj.resolved_at - obj.created_at
            hours = int(delta.total_seconds() // 3600)
            if hours < 1:
                mins = int(delta.total_seconds() // 60)
                return format_html(
                    '<span style="color:#10b981;font-weight:600">{}m</span>', mins
                )
            elif hours < 24:
                return format_html(
                    '<span style="color:#f59e0b;font-weight:600">{}h</span>', hours
                )
            else:
                days = delta.days
                return format_html(
                    '<span style="color:#ef4444;font-weight:600">{}d</span>', days
                )
        return "—"

    # ── Admin actions ────────────────────────────────────────────────────────

    @admin.action(description="✅ Mark selected tickets as Resolved")
    def action_resolve_tickets(self, request, queryset):
        now = timezone.now()
        updated = queryset.exclude(
            status__in=["resolved", "closed"]
        ).update(status="resolved", resolved_at=now)
        self.message_user(
            request,
            f"✅ {updated} ticket(s) marked as resolved.",
            level=messages.SUCCESS,
        )

    @admin.action(description="🔒 Close selected tickets")
    def action_close_tickets(self, request, queryset):
        now = timezone.now()
        updated = queryset.exclude(status="closed").update(
            status="closed", closed_at=now
        )
        self.message_user(
            request,
            f"🔒 {updated} ticket(s) closed.",
            level=messages.SUCCESS,
        )

    @admin.action(description="🚨 Escalate selected tickets (superuser only)")
    def action_escalate_tickets(self, request, queryset):
        if not request.user.is_superuser:
            self.message_user(request, "Superuser only.", level=messages.ERROR)
            return
        updated = queryset.exclude(status="escalated").update(status="escalated")
        self.message_user(
            request,
            f"🚨 {updated} ticket(s) escalated.",
            level=messages.WARNING,
        )

    @admin.action(description="👤 Assign selected tickets to me")
    def action_assign_to_me(self, request, queryset):
        updated = queryset.filter(assigned_to__isnull=True).update(
            assigned_to=request.user
        )
        self.message_user(
            request,
            f"👤 {updated} ticket(s) assigned to you.",
            level=messages.SUCCESS,
        )


# ── Ticket Message Admin ──────────────────────────────────────────────────────

@admin.register(TicketMessage)
class TicketMessageAdmin(admin.ModelAdmin):
    list_display = [
        "id", "ticket", "author", "staff_badge", "body_preview", "created_at",
    ]
    list_filter = ["is_staff_reply"]
    search_fields = ["body", "author__email", "ticket__id"]
    ordering = ["-created_at"]
    date_hierarchy = "created_at"
    list_select_related = ["ticket", "author"]
    raw_id_fields = ["ticket", "author"]
    list_per_page = 25
    show_full_result_count = False
    empty_value_display = "-N/A-"

    readonly_fields = ["id", "created_at"]

    def has_add_permission(self, request):
        return False  # Replies go through the API, not the admin

    def has_change_permission(self, request, obj=None):
        return False

    @admin.display(description="Staff Reply", boolean=True)
    def staff_badge(self, obj):
        return obj.is_staff_reply

    @admin.display(description="Message")
    def body_preview(self, obj):
        return (obj.body or "")[:80] + ("…" if len(obj.body or "") > 80 else "")


# ── Ticket Escalation Admin ───────────────────────────────────────────────────

@admin.register(TicketEscalation)
class TicketEscalationAdmin(admin.ModelAdmin):
    list_display = [
        "id", "ticket", "status_badge", "escalated_by",
        "assigned_admin", "created_at",
    ]
    list_filter = ["status"]
    search_fields = [
        "reason", "resolution_notes",
        "escalated_by__email", "assigned_admin__email",
    ]
    ordering = ["-created_at"]
    date_hierarchy = "created_at"
    list_select_related = ["ticket", "escalated_by", "assigned_admin"]
    raw_id_fields = ["ticket", "escalated_by", "assigned_admin"]
    list_per_page = 25
    show_full_result_count = False
    empty_value_display = "-N/A-"

    readonly_fields = ["id", "created_at", "updated_at"]

    fieldsets = (
        (_("Escalation"), {
            "fields": (
                "ticket", "escalated_by", "reason",
                "assigned_admin", "status",
            ),
        }),
        (_("Resolution"), {
            "fields": ("resolution_notes",),
        }),
        (_("Timestamps"), {
            "fields": ("created_at", "updated_at"),
            "classes": ("collapse",),
        }),
    )

    actions = ["action_resolve_escalations"]

    @admin.display(description="Status")
    def status_badge(self, obj):
        bg, fg = _STATUS_COLOURS.get(obj.status, ("#6b7280", "#fff"))
        label = obj.get_status_display() if hasattr(obj, "get_status_display") else obj.status
        return format_html(
            '<span style="background:{};color:{};padding:2px 8px;'
            'border-radius:20px;font-size:11px;font-weight:600">{}</span>',
            bg, fg, label,
        )

    @admin.action(description="✅ Resolve selected escalations (superuser only)")
    def action_resolve_escalations(self, request, queryset):
        if not request.user.is_superuser:
            self.message_user(request, "Superuser only.", level=messages.ERROR)
            return
        updated = queryset.exclude(status="resolved").update(status="resolved")
        self.message_user(
            request,
            f"✅ {updated} escalation(s) resolved.",
            level=messages.SUCCESS,
        )
