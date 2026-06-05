# apps/custom_order/admin.py
"""
Django Admin for the Custom Order (Bespoke Commission) domain.

Models registered:
  - CustomOrder  : Full bespoke commission contract management
  - CustomOrderMilestone : Payment tranche tracking (read-only ledger)

Production rules:
  - CustomOrder uses SoftDeleteAdminMixin (extends SoftDeleteModel)
  - Milestone rows are immutable — append-only ledger (no add/change/delete)
  - All financial fields are readonly
  - Bulk admin action: cancel selected orders (superuser only)
  - Status badge with colour coding

2026 features:
  - Reference image count displayed in list
  - Paid percentage progress displayed
  - Raw ID for client and vendor (both FK to high-cardinality tables)
"""
import logging

from django.contrib import admin
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from django.contrib import messages
from django.utils.safestring import mark_safe

from apps.common.admin_mixins import SoftDeleteAdminMixin
from apps.custom_order.models import CustomOrder, CustomOrderMilestone

logger = logging.getLogger(__name__)

# ── Status badge colour map ──────────────────────────────────────────────────
_STATUS_COLOURS = {
    "draft":         ("#94a3b8", "#fff"),
    "submitted":     ("#f59e0b", "#fff"),
    "approved":      ("#3b82f6", "#fff"),
    "in_production": ("#8b5cf6", "#fff"),
    "completed":     ("#10b981", "#fff"),
    "cancelled":     ("#ef4444", "#fff"),
    "disputed":      ("#dc2626", "#fff"),
}


# ── Inline: Milestones ────────────────────────────────────────────────────────

class CustomOrderMilestoneInline(admin.TabularInline):
    """Read-only inline — milestones are an immutable payment ledger."""
    model = CustomOrderMilestone
    extra = 0
    readonly_fields = [
        "milestone_pct", "amount_ngn", "payment_status",
        "paid_at", "transaction_ref", "payment_reference",
        "created_at",
    ]
    can_delete = False
    ordering = ["milestone_pct"]

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False


# ── Custom Order Admin ─────────────────────────────────────────────────────────

@admin.register(CustomOrder)
class CustomOrderAdmin(SoftDeleteAdminMixin, admin.ModelAdmin):
    """
    Enterprise-grade admin for bespoke custom orders.

    Provides:
      - Status badge column with colour coding
      - Paid percentage progress indicator
      - Reference image count column
      - Milestone payment tranche inline
      - Bulk cancel action (superuser only)
    """

    list_display = [
        "reference", "status_badge", "client", "vendor",
        "budget_ngn", "agreed_amount_ngn", "currency",
        "paid_progress", "reference_images_preview", "soft_delete_badge",
        "created_at",
    ]
    list_filter = ["status", "currency"]
    search_fields = [
        "reference", "client__email", "vendor__business_name",
    ]
    ordering = ["-created_at"]
    date_hierarchy = "created_at"
    list_select_related = ["client", "vendor"]
    raw_id_fields = ["client", "vendor"]
    list_per_page = 25
    list_max_show_all = 200
    show_full_result_count = False
    empty_value_display = "-N/A-"

    readonly_fields = [
        "id", "reference",
        "budget_ngn", "agreed_amount_ngn",
        "approved_at", "completed_at",
        "is_deleted", "deleted_at", "soft_delete_badge",
        "created_at", "updated_at", "reference_images_preview",
    ]

    fieldsets = (
        (_("Identity"), {
            "fields": ("id", "reference"),
        }),
        (_("Parties"), {
            "fields": ("client", "vendor"),
        }),
        (_("Design Brief"), {
            "fields": ("design_brief", "reference_images", "reference_images_preview"),
        }),
        (_("Style Snapshots"), {
            "fields": ("product_snapshot_id", "order_snapshot_id"),
            "classes": ("collapse",),
        }),
        (_("Financials"), {
            "fields": (
                "budget_ngn", "agreed_amount_ngn", "currency",
            ),
        }),
        (_("Status & Timeline"), {
            "fields": (
                "status", "vendor_approval_note",
                "approved_at", "completed_at",
            ),
        }),
        (_("Soft Delete"), {
            "fields": ("is_deleted", "deleted_at", "soft_delete_badge"),
            "classes": ("collapse",),
        }),
        (_("Timestamps"), {
            "fields": ("created_at", "updated_at"),
            "classes": ("collapse",),
        }),
    )

    inlines = [CustomOrderMilestoneInline]

    actions = ["action_cancel_orders"]

    # ── List display helpers ─────────────────────────────────────────────────

    @admin.display(description="Status")
    def status_badge(self, obj):
        bg, fg = _STATUS_COLOURS.get(obj.status, ("#6b7280", "#fff"))
        return format_html(
            '<span style="background:{};color:{};padding:2px 10px;'
            'border-radius:20px;font-size:11px;font-weight:600">{}</span>',
            bg, fg, obj.get_status_display(),
        )

    @admin.display(description="Paid %")
    def paid_progress(self, obj):
        try:
            pct = obj.paid_pct
        except Exception:
            pct = 0
        
        if pct == 100:
            bg, fg = "#dcfce7", "#166534"
        elif pct > 0:
            bg, fg = "#e0e7ff", "#4338ca"
        else:
            bg, fg = "#f1f5f9", "#475569"
            
        return format_html(
            '<span style="background:{};color:{};padding:2px 8px;'
            'border-radius:20px;font-size:11px;font-weight:700">{}%</span>',
            bg, fg, pct,
        )

    @admin.display(description="Ref. Images")
    def reference_images_preview(self, obj):
        images = obj.reference_images or []
        if not images:
            return "—"
        html_elements = []
        for img_url in images[:3]:
            html_elements.append(
                f'<img src="{img_url}" height="40" style="margin-right:4px;border-radius:4px;object-fit:cover;border:1px solid #e2e8f0;" />'
            )
        if len(images) > 3:
            html_elements.append(f'<span style="font-size:11px;color:#64748b;font-weight:600;">+{len(images)-3}</span>')
        return mark_safe("".join(html_elements))

    # ── Admin actions ────────────────────────────────────────────────────────

    @admin.action(description="🚫 Cancel selected custom orders (superuser only)")
    def action_cancel_orders(self, request, queryset):
        if not request.user.is_superuser:
            self.message_user(
                request,
                "⛔ Only superusers can cancel custom orders.",
                level=messages.ERROR,
            )
            return
        cancelled = 0
        skipped = 0
        for order in queryset:
            try:
                order.cancel()
                cancelled += 1
            except ValueError:
                skipped += 1
        self.message_user(
            request,
            f"✅ {cancelled} order(s) cancelled. "
            f"{skipped} skipped (already completed/cancelled).",
            level=messages.SUCCESS if cancelled > 0 else messages.WARNING,
        )


# ── Custom Order Milestone Admin ───────────────────────────────────────────────

@admin.register(CustomOrderMilestone)
class CustomOrderMilestoneAdmin(admin.ModelAdmin):
    """
    Immutable milestone payment ledger admin.
    No add / change / delete — milestones are auto-seeded by the service layer.
    """

    list_display = [
        "custom_order", "milestone_pct", "amount_ngn",
        "payment_status_badge", "paid_at", "transaction_ref", "created_at",
    ]
    list_filter = ["payment_status", "milestone_pct"]
    search_fields = [
        "custom_order__reference",
        "transaction_ref",
        "payment_reference",
    ]
    ordering = ["custom_order", "milestone_pct"]
    list_select_related = ["custom_order"]
    date_hierarchy = "created_at"
    list_per_page = 25
    show_full_result_count = False
    empty_value_display = "-N/A-"

    readonly_fields = [
        f.name for f in CustomOrderMilestone._meta.get_fields()
        if hasattr(f, "name")
    ]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.display(description="Payment Status")
    def payment_status_badge(self, obj):
        colours = {
            "pending": ("#f59e0b", "#fff"),
            "paid":    ("#10b981", "#fff"),
            "failed":  ("#ef4444", "#fff"),
            "waived":  ("#94a3b8", "#fff"),
        }
        bg, fg = colours.get(obj.payment_status, ("#6b7280", "#fff"))
        return format_html(
            '<span style="background:{};color:{};padding:2px 8px;'
            'border-radius:20px;font-size:11px;font-weight:600">{}</span>',
            bg, fg, obj.get_payment_status_display(),
        )
