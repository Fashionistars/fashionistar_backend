# apps/audit_logs/admin.py
"""
Django admin for AuditEventLog.

Design:
- Immutable: no add / change / delete allowed (audit log must be tamper-proof)
- Rich filters: by event_type, event_category, severity, is_compliance
- Full-text search: actor_email, ip_address, action, resource_id
- Color-coded severity badges + event-type badges
- Superadmin-only access
"""

import logging

from django.contrib import admin
from django.utils.html import format_html

from apps.audit_logs.models import AuditEventLog, SeverityLevel, EventCategory


logger = logging.getLogger(__name__)

# ─── Severity badge colors ──────────────────────────────────────────────────
_SEVERITY_COLORS = {
    SeverityLevel.DEBUG:    ("#6c757d", "⚙"),
    SeverityLevel.INFO:     ("#0d6efd", "ℹ"),
    SeverityLevel.WARNING:  ("#ffc107", "⚠"),
    SeverityLevel.ERROR:    ("#dc3545", "✗"),
    SeverityLevel.CRITICAL: ("#7f0000", "🔴"),
}

_CATEGORY_COLORS = {
    EventCategory.AUTHENTICATION:    "#198754",
    EventCategory.AUTHORIZATION:     "#6f42c1",
    EventCategory.SECURITY:          "#dc3545",
    EventCategory.ADMIN:             "#0dcaf0",
    EventCategory.DATA_MODIFICATION: "#ffc107",
    EventCategory.COMPLIANCE:        "#fd7e14",
}


@admin.register(AuditEventLog)
class AuditEventLogAdmin(admin.ModelAdmin):
    """
    Read-only admin for the AuditEventLog.

    Superadmin access only.  No creation, update, or deletion via admin.
    """

    # ── Display ─────────────────────────────────────────────────────────
    list_display = [
        "created_at",
        "severity_badge",
        "event_category_badge",
        "event_type",
        "actor_email",
        "ip_address",
        "resource_type",
        "response_status",
        "is_compliance",
    ]
    list_display_links = ["created_at", "event_type"]
    readonly_fields = [f.name for f in AuditEventLog._meta.get_fields()
                       if hasattr(f, "column")]
    list_per_page = 50
    date_hierarchy = "created_at"
    show_full_result_count = False  # avoids slow COUNT(*) on large tables

    # ── Filters ──────────────────────────────────────────────────────────
    list_filter = [
        "severity",
        "event_category",
        "event_type",
        "is_compliance",
        "device_type",
        "request_method",
    ]

    # ── Search ───────────────────────────────────────────────────────────
    search_fields = [
        "actor_email",
        "ip_address",
        "action",
        "resource_id",
        "resource_type",
        "request_path",
        "error_message",
    ]

    # ── Field grouping in detail view ─────────────────────────────────────
    fieldsets = [
        ("📋 Event", {
            "fields": (
                "id", "event_type", "event_category", "severity", "action",
                "created_at",
            ),
        }),
        ("👤 Actor", {
            "fields": ("actor", "actor_email"),
        }),
        ("🌐 Request Context", {
            "fields": (
                "ip_address", "user_agent", "device_type",
                "browser_family", "os_family",
                "request_method", "request_path",
                "response_status", "duration_ms",
            ),
        }),
        ("🎯 Resource", {
            "fields": ("resource_type", "resource_id"),
        }),
        ("📊 Change Data", {
            "fields": ("old_values", "new_values", "metadata"),
            "classes": ("collapse",),
        }),
        ("⚠️ Error", {
            "fields": ("error_message",),
            "classes": ("collapse",),
        }),
        ("🔒 Compliance", {
            "fields": ("is_compliance", "retention_days"),
        }),
    ]

    # ── Permissions — read-only superadmin only ──────────────────────────

    def has_module_perms(self, request, app_label=None):
        return request.user.is_superuser

    def has_view_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_add_permission(self, request):
        return False  # Audit logs are never created via admin

    def has_change_permission(self, request, obj=None):
        return False  # Immutable — no edits allowed

    def has_delete_permission(self, request, obj=None):
        return False  # Immutable — no deletions via admin

    # ── Badge helpers ─────────────────────────────────────────────────────

    @admin.display(description="Severity", ordering="severity")
    def severity_badge(self, obj):
        color, icon = _SEVERITY_COLORS.get(obj.severity, ("#6c757d", "?"))
        label = obj.get_severity_display()
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 8px;'
            'border-radius:12px;font-size:11px;font-weight:700;">'
            '{} {}'
            '</span>',
            color, icon, label,
        )

    @admin.display(description="Category", ordering="event_category")
    def event_category_badge(self, obj):
        color = _CATEGORY_COLORS.get(obj.event_category, "#6c757d")
        label = obj.get_event_category_display()
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 8px;'
            'border-radius:12px;font-size:11px;font-weight:600;">'
            '{}'
            '</span>',
            color, label,
        )
