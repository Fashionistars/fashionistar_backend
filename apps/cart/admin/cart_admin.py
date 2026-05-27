# apps/cart/admin/cart_admin.py
from django.contrib import admin

from apps.common.admin_ui import FashionistarAdminUIMixin
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


@admin.register(CartItem)
class CartItemAdmin(FashionistarAdminUIMixin, admin.ModelAdmin):
    list_display = [
        "cart",
        "product",
        "variant",
        "quantity",
        "unit_price",
        "line_total_display",
        "is_saved_for_later",
        "created_at",
    ]
    list_filter = ["is_saved_for_later", "product__vendor"]
    search_fields = [
        "cart__user__email",
        "cart__session_key",
        "product__title",
        "product__sku",
        "idempotency_key",
    ]
    list_select_related = ["cart", "product", "variant"]
    readonly_fields = [f.name for f in CartItem._meta.get_fields() if hasattr(f, "name")]
    ordering = ["-created_at"]
    date_hierarchy = "created_at"

    @admin.display(description="Line Total")
    def line_total_display(self, obj):
        return self.format_ngn(obj.line_total)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
