# apps/audit_logs/admin.py
"""
Django admin for AuditEventLog.

Design:
- Immutable: no add / change / delete allowed (audit log must be tamper-proof)
- Rich filters: by event_type, event_category, severity, is_compliance
- Full-text search: actor_email, ip_address, action, resource_id
- Color-coded severity badges + event-type badges
- Superadmin-only access
- E5: Streaming CSV compliance export action (superuser only, date-range filtered)
"""

from __future__ import annotations

import csv
import logging

from django.contrib import admin
from django.http import StreamingHttpResponse
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


# ═══════════════════════════════════════════════════════════════════════════
# E5 — Compliance CSV Export (streaming, superuser-only)
# ═══════════════════════════════════════════════════════════════════════════

class _EchoWriter:
    """Pseudo-buffer for csv.writer + StreamingHttpResponse."""
    def write(self, value):
        return value


def _compliance_csv_rows(queryset):
    """
    Generator: yields header row then one row per AuditEventLog in queryset.
    Uses queryset.iterator(chunk_size=500) to avoid loading all rows into RAM.
    """
    FIELDS = [
        "id", "created_at", "event_type", "event_category", "severity",
        "actor_email", "ip_address", "country", "action",
        "resource_type", "resource_id", "response_status",
        "correlation_id", "is_compliance", "error_message",
    ]
    yield FIELDS
    for obj in queryset.only(*FIELDS).iterator(chunk_size=500):
        yield [
            str(getattr(obj, f, "") or "")
            for f in FIELDS
        ]


@admin.action(description="📥 Export compliance logs as CSV (superuser only)")
def export_compliance_logs_csv(modeladmin, request, queryset):
    """
    E5 — Streaming CSV export of selected AuditEventLog rows.

    Guards:
    - Superuser only: returns 403 for staff
    - Only exports compliance=True events (auto-filtered)
    - Uses streaming CSV for memory efficiency (100k+ rows safe)
    - Filename includes timestamp for audit trail

    Usage:
        1. In AuditEventLog changelist, select rows (or select all)
        2. Choose "Export compliance logs as CSV" from Actions dropdown
        3. Click Go → immediate file download
    """
    from django.http import HttpResponseForbidden
    from django.utils import timezone

    if not request.user.is_superuser:
        return HttpResponseForbidden("Superuser required for compliance export.")

    # Filter to compliance events only (regardless of what user selected)
    compliance_qs = queryset.filter(is_compliance=True).order_by("-created_at")

    pseudo_buffer = _EchoWriter()
    writer = csv.writer(pseudo_buffer)

    def stream():
        for row in _compliance_csv_rows(compliance_qs):
            yield writer.writerow(row)

    timestamp = timezone.now().strftime("%Y%m%d_%H%M%S")
    filename = f"fashionistar_compliance_audit_{timestamp}.csv"

    response = StreamingHttpResponse(stream(), content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    response["X-Compliance-Export"] = "true"
    return response


# ═══════════════════════════════════════════════════════════════════════════
# AuditEventLog Admin
# ═══════════════════════════════════════════════════════════════════════════

@admin.register(AuditEventLog)
class AuditEventLogAdmin(admin.ModelAdmin):
    """
    Read-only, superadmin-only admin for AuditEventLog.

    Features:
    • Color-coded severity + category badges
    • Full-text search on actor_email, ip_address, action, resource_id
    • Filterable by event_type, event_category, severity, is_compliance, country
    • date_hierarchy for fast temporal browsing
    • Collapsible diff / metadata JSON in detail view
    • E5: streaming CSV compliance export action
    """

    # ── Bulk actions ────────────────────────────────────────────────────────
    actions = [export_compliance_logs_csv]

    # ── List view ───────────────────────────────────────────────────────────
    list_display = (
        "created_at",
        "severity_badge",
        "event_category_badge",
        "event_type",
        "actor_email",
        "ip_address",
        "country",
        "action",
        "response_status",
        "is_compliance",
    )
    list_filter = (
        "severity",
        "event_type",
        "event_category",
        "is_compliance",
        "country",
    )
    search_fields = (
        "actor_email",
        "ip_address",
        "action",
        "resource_id",
        "correlation_id",
        "error_message",
    )
    ordering = ("-created_at",)
    date_hierarchy = "created_at"
    list_per_page = 50
    show_full_result_count = False   # Avoids COUNT(*) on large tables

    # ── Detail view ─────────────────────────────────────────────────────────
    readonly_fields = (
        "id",
        "created_at",
        "event_type",
        "event_category",
        "severity",
        "actor",
        "actor_email",
        "ip_address",
        "country",
        "user_agent",
        "device_fingerprint",
        "request_method",
        "request_path",
        "response_status",
        "action",
        "resource_type",
        "resource_id",
        "old_values",
        "new_values",
        "metadata",
        "error_message",
        "is_compliance",
        "retention_days",
        "correlation_id",
    )

    fieldsets = (
        ("Event Identity", {
            "fields": (
                "id", "created_at", "event_type", "event_category", "severity",
                "is_compliance", "correlation_id",
            ),
        }),
        ("Actor", {
            "fields": ("actor", "actor_email"),
        }),
        ("Request Context", {
            "fields": (
                "ip_address", "country", "user_agent", "device_fingerprint",
                "request_method", "request_path", "response_status",
            ),
        }),
        ("Action", {
            "fields": ("action", "resource_type", "resource_id"),
        }),
        ("Diff & Metadata", {
            "classes": ("collapse",),
            "fields": ("old_values", "new_values", "metadata", "error_message"),
        }),
        ("Retention", {
            "classes": ("collapse",),
            "fields": ("retention_days",),
        }),
    )

    # ── Permissions (immutable, superuser-only) ─────────────────────────────

    def has_module_perms(self, request):
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
