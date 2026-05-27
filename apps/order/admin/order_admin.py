# apps/order/admin/order_admin.py
"""
Order domain admin.

Models registered:
  - Order                 : Full order lifecycle management
  - CartOrderItem         : Line-item audit view (read-only)
  - OrderStatusHistory    : Status transition log (append-only)
  - OrderIdempotencyRecord: Duplicate payment guard (read-only)

Design decisions:
  - OrderStatusHistory is append-only: all write permissions disabled.
  - OrderItem is read-only inline (snapshots must not be mutated).
  - Bulk actions for admin status override and CSV export.
  - Financial fields readonly to prevent manual manipulation.
  - list_select_related prevents N+1 on user/vendor FK columns.
"""
import logging

from django.contrib import admin
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from django.contrib import messages
from django.http import StreamingHttpResponse
import csv

from apps.common.admin_ui import FashionistarAdminUIMixin
from apps.order.models import (
    CartOrderItem,
    Order,
    OrderCommercialTransitionLog,
    OrderIdempotencyRecord,
    OrderPaymentRecord,
    OrderStatusHistory,
)

logger = logging.getLogger(__name__)
OrderItem = CartOrderItem  # alias used through this admin module


class OrderItemInline(admin.TabularInline):
    model = CartOrderItem
    extra = 0
    readonly_fields = [
        "product", "variant", "vendor",
        "product_title_snapshot", "product_sku_snapshot", "variant_description_snapshot",
        "unit_price", "quantity", "commission_rate",
        "commission_amount", "line_total", "is_custom_order",
    ]
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


class OrderStatusHistoryInline(admin.TabularInline):
    model = OrderStatusHistory
    extra = 0
    readonly_fields = ["from_status", "to_status", "actor", "note", "created_at"]
    can_delete = False
    ordering = ["created_at"]

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False


class OrderPaymentRecordInline(admin.TabularInline):
    model = OrderPaymentRecord
    extra = 0
    can_delete = False
    readonly_fields = [
        "sequence_number",
        "payment_source",
        "provider",
        "selected_percent",
        "applied_percent",
        "amount",
        "currency",
        "cumulative_amount_paid",
        "cumulative_percent_paid",
        "remaining_amount",
        "remaining_percent",
        "is_final_payment",
        "paid_at",
        "actor",
        "correlation_id",
    ]
    ordering = ["sequence_number", "created_at"]

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False


class OrderCommercialTransitionLogInline(admin.TabularInline):
    model = OrderCommercialTransitionLog
    extra = 0
    can_delete = False
    readonly_fields = [
        "transition_type",
        "from_status",
        "to_status",
        "payment_record",
        "selected_percent",
        "cumulative_percent_paid",
        "amount_delta",
        "balance_after",
        "actor",
        "occurred_at",
        "correlation_id",
    ]
    ordering = ["occurred_at", "created_at"]

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = [
        "order_number", "status_badge", "user", "vendor",
        "total_amount", "currency", "payment_reference",
        "escrow_released", "paid_at", "created_at",
    ]
    list_filter = ["status", "fulfillment_type", "currency", "escrow_released", "is_test_order"]
    search_fields = ["order_number", "payment_reference", "user__email", "vendor__business_name"]
    ordering = ["-created_at"]
    date_hierarchy = "created_at"
    list_select_related = ["user", "vendor"]
    raw_id_fields = ["user", "vendor"]
    list_per_page = 25
    list_max_show_all = 200
    show_full_result_count = False
    empty_value_display = "-N/A-"
    readonly_fields = [
        "order_number", "idempotency_key",
        "subtotal", "shipping_amount", "discount_amount",
        "total_amount", "commission_amount", "vendor_payout",
        "payment_reference", "payment_gateway", "paid_at",
        "coupon_code", "tracking_number", "escrow_released",
        "created_at", "updated_at",
    ]
    inlines = [
        OrderItemInline,
        OrderStatusHistoryInline,
        OrderPaymentRecordInline,
        OrderCommercialTransitionLogInline,
    ]
    fieldsets = (
        ("Identity", {
            "fields": ("order_number", "idempotency_key", "status", "fulfillment_type", "is_test_order"),
        }),
        ("Actors", {
            "fields": ("user", "vendor"),
        }),
        ("Financials", {
            "fields": (
                "subtotal", "shipping_amount", "discount_amount",
                "total_amount", "commission_amount", "vendor_payout", "currency",
            ),
        }),
        ("Payment", {
            "fields": ("payment_reference", "payment_gateway", "paid_at", "coupon_code"),
        }),
        ("Delivery", {
            "fields": ("delivery_address", "courier", "tracking_number", "estimated_delivery"),
        }),
        ("Flags", {
            "fields": ("escrow_released", "measurement_profile_id", "notes"),
        }),
        ("Timestamps", {
            "fields": ("created_at", "updated_at"),
            "classes": ("collapse",),
        }),
    )

    actions = ["action_export_csv"]

    @admin.display(description="Status")
    def status_badge(self, obj):
        color_map = {
            "pending_payment":   "#f59e0b",
            "payment_confirmed": "#3b82f6",
            "processing":        "#8b5cf6",
            "shipped":           "#06b6d4",
            "out_for_delivery":  "#0ea5e9",
            "delivered":         "#10b981",
            "completed":         "#22c55e",
            "cancelled":         "#ef4444",
            "refund_requested":  "#f97316",
            "refunded":          "#6b7280",
            "disputed":          "#dc2626",
        }
        color = color_map.get(obj.status, "#6b7280")
        return format_html(
            '<span style="background:{};color:white;padding:2px 8px;'
            'border-radius:20px;font-size:11px;font-weight:600">{}</span>',
            color, obj.get_status_display(),
        )

    @admin.action(description="📥 Export selected orders to CSV")
    def action_export_csv(self, request, queryset):
        fields = [
            "order_number", "status", "user__email",
            "vendor__business_name", "total_amount", "currency",
            "payment_reference", "paid_at", "created_at",
        ]

        def stream():
            import io
            yield ",".join(fields) + "\n"
            for row in queryset.values(*fields).iterator():
                buf = io.StringIO()
                w = csv.writer(buf)
                w.writerow([str(row.get(f, "") or "") for f in fields])
                yield buf.getvalue()

        response = StreamingHttpResponse(stream(), content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="orders.csv"'
        return response


@admin.register(CartOrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = [
        "order", "product_title_snapshot", "vendor",
        "quantity", "unit_price", "line_total", "commission_amount",
    ]
    list_filter = ["is_custom_order"]
    search_fields = ["order__order_number", "product_title_snapshot", "product_sku_snapshot"]
    ordering = ["-order__created_at"]
    date_hierarchy = "order__created_at"
    list_select_related = ["order", "vendor"]
    list_per_page = 25
    show_full_result_count = False
    empty_value_display = "-N/A-"
    readonly_fields = [f.name for f in CartOrderItem._meta.get_fields() if hasattr(f, "name")]

    fieldsets = (
        (_("Order Context"), {
            "fields": ("order", "vendor", "is_custom_order"),
        }),
        (_("Product Snapshot"), {
            "fields": (
                "product_title_snapshot", "product_sku_snapshot",
                "variant_description_snapshot",
                "product", "variant",
            ),
        }),
        (_("Financials"), {
            "fields": (
                "quantity", "unit_price", "line_total",
                "commission_rate", "commission_amount",
            ),
        }),
    )

    def has_add_permission(self, request): return False
    def has_change_permission(self, request, obj=None): return False
    def has_delete_permission(self, request, obj=None): return False


@admin.register(OrderStatusHistory)
class OrderStatusHistoryAdmin(admin.ModelAdmin):
    list_display = ["order", "from_status", "to_status", "actor", "created_at"]
    list_filter = ["to_status", "from_status"]
    search_fields = ["order__order_number", "actor__email", "note"]
    ordering = ["-created_at"]
    date_hierarchy = "created_at"
    list_select_related = ["order", "actor"]
    list_per_page = 25
    show_full_result_count = False
    empty_value_display = "-N/A-"
    readonly_fields = [f.name for f in OrderStatusHistory._meta.get_fields() if hasattr(f, "name")]

    def has_add_permission(self, request): return False
    def has_change_permission(self, request, obj=None): return False
    def has_delete_permission(self, request, obj=None): return False


@admin.register(OrderIdempotencyRecord)
class OrderIdempotencyRecordAdmin(admin.ModelAdmin):
    """
    Read-only admin for duplicate order creation guard records.
    Prevents double-orders on network retries or duplicate form submissions.
    Actual fields: key (char), order (OneToOne FK), expires_at.
    """
    list_display = [
        "key_short", "order", "expires_at", "created_at",
    ]
    list_filter = []
    search_fields = [
        "key", "order__order_number",
    ]
    ordering = ["-created_at"]
    date_hierarchy = "created_at"
    list_select_related = ["order"]
    list_per_page = 25
    show_full_result_count = False
    empty_value_display = "-N/A-"
    readonly_fields = [
        f.name for f in OrderIdempotencyRecord._meta.get_fields()
        if hasattr(f, "name")
    ]

    @admin.display(description="Key")
    def key_short(self, obj):
        k = obj.key or ""
        return f"{k[:16]}…" if len(k) > 16 else k

    def has_add_permission(self, request): return False
    def has_change_permission(self, request, obj=None): return False
    def has_delete_permission(self, request, obj=None): return False


@admin.register(OrderPaymentRecord)
class OrderPaymentRecordAdmin(FashionistarAdminUIMixin, admin.ModelAdmin):
    list_display = [
        "order",
        "sequence_number",
        "payment_source",
        "selected_percent",
        "amount_display",
        "cumulative_percent_paid",
        "is_final_payment",
        "paid_at",
    ]
    list_filter = ["payment_source", "provider", "is_final_payment", "currency"]
    search_fields = ["order__order_number", "correlation_id", "payment_intent__reference"]
    list_select_related = ["order", "payment_intent", "actor"]
    raw_id_fields = ["order", "payment_intent", "actor"]
    readonly_fields = [f.name for f in OrderPaymentRecord._meta.get_fields() if hasattr(f, "name")]
    ordering = ["-paid_at", "-created_at"]
    date_hierarchy = "paid_at"

    @admin.display(description="Amount")
    def amount_display(self, obj):
        return self.format_ngn(obj.amount)

    def has_add_permission(self, request): return False
    def has_change_permission(self, request, obj=None): return False
    def has_delete_permission(self, request, obj=None): return False


@admin.register(OrderCommercialTransitionLog)
class OrderCommercialTransitionLogAdmin(FashionistarAdminUIMixin, admin.ModelAdmin):
    list_display = [
        "order",
        "transition_type",
        "from_status",
        "to_status",
        "amount_delta_display",
        "balance_after_display",
        "actor_role",
        "occurred_at",
    ]
    list_filter = ["transition_type", "delivery_mode", "cash_payment_mode_snapshot", "actor_role"]
    search_fields = ["order__order_number", "correlation_id", "note", "actor__email"]
    list_select_related = ["order", "payment_record", "payment_intent", "actor"]
    raw_id_fields = ["order", "payment_record", "payment_intent", "actor"]
    readonly_fields = [f.name for f in OrderCommercialTransitionLog._meta.get_fields() if hasattr(f, "name")]
    ordering = ["-occurred_at", "-created_at"]
    date_hierarchy = "occurred_at"

    @admin.display(description="Amount Delta")
    def amount_delta_display(self, obj):
        return self.format_ngn(obj.amount_delta)

    @admin.display(description="Balance After")
    def balance_after_display(self, obj):
        return self.format_ngn(obj.balance_after)

    def has_add_permission(self, request): return False
    def has_change_permission(self, request, obj=None): return False
    def has_delete_permission(self, request, obj=None): return False
