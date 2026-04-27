# apps/cart/admin/cart_admin.py
from django.contrib import admin
from apps.cart.models import Cart, CartItem, CartActivityLog


class CartItemInline(admin.TabularInline):
    model = CartItem
    extra = 0
    readonly_fields = ["product", "variant", "quantity", "unit_price", "line_total", "idempotency_key", "is_saved_for_later"]

    def line_total(self, obj):
        return obj.line_total
    line_total.short_description = "Line Total"

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    list_display = ["user", "item_count", "subtotal", "total", "coupon", "last_activity"]
    search_fields = ["user__email"]
    readonly_fields = ["user", "subtotal", "total", "item_count", "coupon_discount", "last_activity", "created_at", "updated_at"]
    inlines = [CartItemInline]


@admin.register(CartActivityLog)
class CartActivityLogAdmin(admin.ModelAdmin):
    list_display = ["cart", "action", "product", "quantity", "created_at"]
    list_filter = ["action"]
    readonly_fields = [f.name for f in CartActivityLog._meta.get_fields() if hasattr(f, "name")]

    def has_add_permission(self, request): return False
    def has_change_permission(self, request, obj=None): return False
    def has_delete_permission(self, request, obj=None): return False
