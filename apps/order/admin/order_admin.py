# apps/order/admin/order_admin.py
"""
Order domain admin.

Design decisions:
  - OrderStatusHistory is append-only: all write permissions disabled.
  - OrderItem is read-only inline (snapshots must not be mutated).
  - Bulk actions for admin status override.
  - Financial fields readonly to prevent manual manipulation.
"""
from django.contrib import admin
from django.utils.html import format_html

from apps.order.models import Order, OrderItem, OrderStatusHistory, OrderIdempotencyRecord


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = [
        "product", "variant", "vendor",
        "product_title", "product_sku", "variant_description",
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
    readonly_fields = [
        "order_number", "idempotency_key",
        "subtotal", "shipping_amount", "discount_amount",
        "total_amount", "commission_amount", "vendor_payout",
        "payment_reference", "payment_gateway", "paid_at",
        "coupon_code", "tracking_number", "escrow_released",
        "created_at", "updated_at",
    ]
    inlines = [OrderItemInline, OrderStatusHistoryInline]
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

    @admin.display(description="Status")
    def status_badge(self, obj):
        color_map = {
            "pending_payment": "#f59e0b",
            "payment_confirmed": "#3b82f6",
            "processing": "#8b5cf6",
            "shipped": "#06b6d4",
            "out_for_delivery": "#0ea5e9",
            "delivered": "#10b981",
            "completed": "#22c55e",
            "cancelled": "#ef4444",
            "refund_requested": "#f97316",
            "refunded": "#6b7280",
            "disputed": "#dc2626",
        }
        color = color_map.get(obj.status, "#6b7280")
        return format_html(
            '<span style="background:{};color:white;padding:2px 8px;border-radius:4px;font-size:11px">{}</span>',
            color, obj.get_status_display(),
        )

    def get_actions(self, request):
        actions = super().get_actions(request)
        return actions


@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = ["order", "product_title", "quantity", "unit_price", "line_total", "commission_amount"]
    search_fields = ["order__order_number", "product_title", "product_sku"]
    readonly_fields = [f.name for f in OrderItem._meta.get_fields() if hasattr(f, "name")]

    def has_add_permission(self, request): return False
    def has_change_permission(self, request, obj=None): return False
    def has_delete_permission(self, request, obj=None): return False


@admin.register(OrderStatusHistory)
class OrderStatusHistoryAdmin(admin.ModelAdmin):
    list_display = ["order", "from_status", "to_status", "actor", "created_at"]
    list_filter = ["to_status"]
    readonly_fields = [f.name for f in OrderStatusHistory._meta.get_fields() if hasattr(f, "name")]

    def has_add_permission(self, request): return False
    def has_change_permission(self, request, obj=None): return False
    def has_delete_permission(self, request, obj=None): return False
