# apps/product/admin/product_admin.py
"""
Django admin configuration for the Product domain.

Uses CloudinaryWidget for inline media previews and
role-aware list filtering for vendor management.
"""

from django.contrib import admin
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from apps.product.models import (
    Product,
    ProductGalleryMedia,
    ProductVariant,
    ProductSpecification,
    ProductFaq,
    ProductReview,
    ProductWishlist,
    ProductInventoryLog,
    ProductTag,
    ProductSize,
    ProductColor,
    Coupon,
    DeliveryCourier,
    ProductCommissionSnapshot,
)


# ─── Inlines ──────────────────────────────────────────────────────────────────

class ProductGalleryMediaInline(admin.TabularInline):
    model = ProductGalleryMedia
    extra = 0
    fields = ["media", "media_preview", "media_type", "alt_text", "ordering", "is_deleted"]
    readonly_fields = ["media_preview"]

    def media_preview(self, obj):
        if obj.media:
            return format_html('<img src="{}" height="60" />', obj.media.url)
        return "—"
    media_preview.short_description = "Preview"


class ProductVariantInline(admin.TabularInline):
    model = ProductVariant
    extra = 0
    fields = ["sku", "size", "color", "price_override", "stock_qty", "is_active"]


class ProductSpecificationInline(admin.TabularInline):
    model = ProductSpecification
    extra = 0
    fields = ["title", "content"]


class ProductFaqInline(admin.TabularInline):
    model = ProductFaq
    extra = 0
    fields = ["question", "answer"]


# ─── Product Admin ────────────────────────────────────────────────────────────

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = [
        "title", "vendor", "status", "price", "currency",
        "stock_qty", "in_stock", "featured", "rating", "review_count",
        "is_deleted", "created_at",
    ]
    list_filter = ["status", "featured", "in_stock", "is_deleted", "category", "brand"]
    search_fields = ["title", "slug", "sku", "vendor__business_name"]
    prepopulated_fields = {"slug": ("title",)}
    readonly_fields = [
        "id", "sku", "views", "orders_count", "rating", "review_count",
        "created_at", "updated_at", "is_deleted", "deleted_at", "image_preview",
    ]
    fieldsets = (
        (_("Identity"), {
            "fields": ("id", "title", "slug", "sku", "description", "short_description"),
        }),
        (_("Taxonomy"), {
            "fields": ("vendor", "category", "sub_category", "brand", "tags", "sizes", "colors"),
        }),
        (_("Pricing"), {
            "fields": ("price", "old_price", "currency", "shipping_amount", "commission_rate"),
        }),
        (_("Inventory"), {
            "fields": ("stock_qty", "in_stock", "requires_measurement", "is_customisable"),
        }),
        (_("Media"), {
            "fields": ("image", "image_preview"),
        }),
        (_("Status & Flags"), {
            "fields": ("status", "featured", "hot_deal", "digital"),
        }),
        (_("Metrics"), {
            "fields": ("views", "orders_count", "rating", "review_count"),
        }),
        (_("Lifecycle"), {
            "fields": ("created_at", "updated_at", "is_deleted", "deleted_at"),
        }),
    )
    filter_horizontal = ["tags", "sizes", "colors"]
    inlines = [
        ProductGalleryMediaInline,
        ProductVariantInline,
        ProductSpecificationInline,
        ProductFaqInline,
    ]
    actions = ["publish_selected", "archive_selected"]

    def image_preview(self, obj):
        if obj.image:
            return format_html('<img src="{}" height="100" />', obj.image.url)
        return "—"
    image_preview.short_description = "Image Preview"

    @admin.action(description="Publish selected products")
    def publish_selected(self, request, queryset):
        from apps.product.services import approve_product
        count = 0
        for product in queryset:
            try:
                approve_product(product=product, actor=request.user)
                count += 1
            except Exception:
                pass
        self.message_user(request, f"{count} product(s) published.")

    @admin.action(description="Archive selected products")
    def archive_selected(self, request, queryset):
        from apps.product.services import archive_product
        count = 0
        for product in queryset:
            try:
                archive_product(product=product, actor=request.user)
                count += 1
            except Exception:
                pass
        self.message_user(request, f"{count} product(s) archived.")


# ─── Review Admin ─────────────────────────────────────────────────────────────

@admin.register(ProductReview)
class ProductReviewAdmin(admin.ModelAdmin):
    list_display = ["product", "reviewer_name", "rating", "active", "moderated", "created_at"]
    list_filter = ["active", "moderated", "rating"]
    search_fields = ["product__title", "reviewer_name", "reviewer_email", "review"]
    readonly_fields = ["created_at", "updated_at"]
    actions = ["moderate_selected", "deactivate_selected"]

    @admin.action(description="Mark selected reviews as moderated")
    def moderate_selected(self, request, queryset):
        queryset.update(moderated=True)

    @admin.action(description="Deactivate selected reviews")
    def deactivate_selected(self, request, queryset):
        queryset.update(active=False)


# ─── Coupon Admin ─────────────────────────────────────────────────────────────

@admin.register(Coupon)
class CouponAdmin(admin.ModelAdmin):
    list_display = [
        "code", "vendor", "discount_type", "discount_value",
        "usage_count", "usage_limit", "active", "valid_from", "valid_to",
    ]
    list_filter = ["discount_type", "active"]
    search_fields = ["code", "vendor__business_name"]
    readonly_fields = ["usage_count", "created_at", "updated_at"]


# ─── Delivery Courier Admin ───────────────────────────────────────────────────

@admin.register(DeliveryCourier)
class DeliveryCourierAdmin(admin.ModelAdmin):
    list_display = ["name", "base_fee", "estimated_days_min", "estimated_days_max", "active"]
    list_filter = ["active"]
    search_fields = ["name"]


# ─── Reference data admin ─────────────────────────────────────────────────────

@admin.register(ProductTag)
class ProductTagAdmin(admin.ModelAdmin):
    list_display = ["name", "slug", "category"]
    prepopulated_fields = {"slug": ("name",)}
    search_fields = ["name"]


@admin.register(ProductSize)
class ProductSizeAdmin(admin.ModelAdmin):
    list_display = ["name"]
    search_fields = ["name"]


@admin.register(ProductColor)
class ProductColorAdmin(admin.ModelAdmin):
    list_display = ["name", "hex_code"]
    search_fields = ["name"]


@admin.register(ProductInventoryLog)
class ProductInventoryLogAdmin(admin.ModelAdmin):
    list_display = ["product", "quantity_delta", "quantity_before", "quantity_after", "reason", "created_at"]
    list_filter = ["reason"]
    search_fields = ["product__title", "reference_id"]
    readonly_fields = [f.name for f in ProductInventoryLog._meta.get_fields() if hasattr(f, "name")]

    def has_add_permission(self, request):
        return False  # Append-only via service

    def has_change_permission(self, request, obj=None):
        return False  # Immutable

    def has_delete_permission(self, request, obj=None):
        return False  # Never delete audit trail
