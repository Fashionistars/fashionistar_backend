# apps/order/admin/order_2026_admin.py
"""
Admin registrations for Phase 4 (2026) order models:
  - OrderTimeline: Immutable status transition log (read-only admin).
  - OrderDispute: Escrow-hold dispute + moderator resolution workflow.
  - DiscountCode: Platform/vendor promo code management.

Conventions:
  - AuditedModelAdmin + admin.ModelAdmin for full audit trail.
  - OrderTimeline: add + change permissions disabled (append-only by service layer).
  - OrderDispute: moderator resolution fields exposed on change_view.
  - DiscountCode: full CRUD with usage stats readonly.
"""

from django.contrib import admin
from django.utils import timezone
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from apps.audit_logs.mixins import AuditedModelAdmin
from apps.order.models import DiscountCode, OrderDispute, OrderTimeline


# ─────────────────────────────────────────────────────────────────────────────
# ORDER TIMELINE (read-only immutable log)
# ─────────────────────────────────────────────────────────────────────────────


class OrderTimelineInline(admin.TabularInline):
    """
    Inline for OrderTimeline — displayed inside OrderAdmin change view.
    Immutable: no add / edit / delete.
    """

    model = OrderTimeline
    extra = 0
    fields = ["from_status", "to_status", "actor", "note", "is_system_event", "created_at"]
    readonly_fields = ["from_status", "to_status", "actor", "note", "is_system_event", "created_at"]
    ordering = ["-created_at"]
    can_delete = False
    show_change_link = False

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(OrderTimeline)
class OrderTimelineAdmin(AuditedModelAdmin, admin.ModelAdmin):
    """
    Read-only admin for OrderTimeline. Records are created only by OrderService.
    Superusers can view; no add/change/delete for anyone.
    """

    list_display = [
        "order_link",
        "from_status",
        "to_status",
        "actor",
        "note_short",
        "is_system_event",
        "created_at",
    ]
    list_filter = ["to_status", "from_status", "is_system_event"]
    search_fields = ["order__id", "actor__email", "note"]
    readonly_fields = [
        "order", "from_status", "to_status", "actor",
        "actor_role", "actor_ip", "note", "is_system_event",
        "metadata", "created_at", "updated_at",
    ]

    def order_link(self, obj):
        return format_html(
            '<a href="/admin/order/order/{}/change/">Order #{}</a>',
            obj.order_id, str(obj.order_id)[:8]
        )
    order_link.short_description = _("Order")

    def note_short(self, obj):
        return (obj.note or "")[:60] + ("…" if obj.note and len(obj.note) > 60 else "")
    note_short.short_description = _("Note")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser


# ─────────────────────────────────────────────────────────────────────────────
# ORDER DISPUTE
# ─────────────────────────────────────────────────────────────────────────────


@admin.action(description="Mark selected disputes as RESOLVED")
def resolve_disputes(modeladmin, request, queryset):
    """Bulk resolve disputes — moderator action."""
    queryset.filter(status=OrderDispute.Status.OPEN).update(
        status=OrderDispute.Status.RESOLVED,
        resolved_by=request.user,
        resolved_at=timezone.now(),
    )


@admin.action(description="Escalate selected disputes to ESCALATED")
def escalate_disputes(modeladmin, request, queryset):
    queryset.filter(status=OrderDispute.Status.OPEN).update(
        status=OrderDispute.Status.ESCALATED
    )


@admin.register(OrderDispute)
class OrderDisputeAdmin(AuditedModelAdmin, admin.ModelAdmin):
    """
    Admin for OrderDispute — moderator resolution workflow.
    """

    list_display = [
        "order_link",
        "opened_by",
        "status",
        "reason",
        "escrow_held",
        "refund_amount",
        "assigned_moderator",
        "created_at",
        "resolved_at",
        "sla_deadline",
    ]
    list_filter = ["status", "reason", "escrow_held"]
    list_editable = ["status"]
    search_fields = ["order__id", "opened_by__email", "description"]
    readonly_fields = [
        "order", "opened_by", "escrow_held", "created_at", "updated_at",
    ]
    actions = [resolve_disputes, escalate_disputes]

    fieldsets = (
        (_("Dispute"), {"fields": ("order", "opened_by", "reason", "description")}),
        (_("Evidence"), {"fields": ("client_evidence", "vendor_evidence")}),
        (_("Financials"), {"fields": ("escrow_held", "refund_amount")}),
        (_("Resolution"), {
            "fields": ("status", "resolution_outcome", "resolution_note", "assigned_moderator", "resolved_at", "sla_deadline"),
        }),
        (_("System"), {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )

    def order_link(self, obj):
        return format_html(
            '<a href="/admin/order/order/{}/change/">Order #{}</a>',
            obj.order_id, str(obj.order_id)[:8]
        )
    order_link.short_description = _("Order")


# ─────────────────────────────────────────────────────────────────────────────
# DISCOUNT CODE
# ─────────────────────────────────────────────────────────────────────────────


@admin.action(description="Activate selected discount codes")
def activate_codes(modeladmin, request, queryset):
    queryset.update(is_active=True)


@admin.action(description="Deactivate selected discount codes")
def deactivate_codes(modeladmin, request, queryset):
    queryset.update(is_active=False)


@admin.register(DiscountCode)
class DiscountCodeAdmin(AuditedModelAdmin, admin.ModelAdmin):
    """
    Admin for DiscountCode — platform and vendor promo management.
    Tracks current_uses vs max_uses atomically in real time.
    """

    list_display = [
        "code",
        "discount_type",
        "discount_value",
        "current_uses",
        "max_uses",
        "is_active",
        "vendor",
        "valid_from",
        "valid_until",
        "created_at",
    ]
    list_filter = ["discount_type", "is_active", "valid_from", "valid_until"]
    list_editable = ["is_active"]
    search_fields = ["code", "description"]
    readonly_fields = ["current_uses", "created_at", "updated_at"]
    actions = [activate_codes, deactivate_codes]

    fieldsets = (
        (_("Code"), {"fields": ("code", "description")}),
        (_("Discount"), {"fields": ("discount_type", "discount_value", "max_discount_amount", "minimum_order_value")}),
        (_("Validity"), {"fields": ("is_active", "is_first_order_only", "valid_from", "valid_until")}),
        (_("Usage"), {"fields": ("max_uses", "max_uses_per_user", "current_uses")}),
        (_("Scope"), {"fields": ("vendor", "created_by"), "classes": ("collapse",)}),
        (_("Metadata"), {"fields": ("metadata",), "classes": ("collapse",)}),
        (_("Timestamps"), {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )
