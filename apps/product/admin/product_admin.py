# apps/product/admin/product_admin.py
"""
Django admin configuration for the Product domain — Enterprise Edition.

All admin classes use:
  - SoftDelete-aware queryset (shows is_deleted flag)
  - Cloudinary inline media previews
  - Custom actions with service-layer calls (instead of raw queryset updates)
  - Append-only / immutable enforcement on audit tables
  - Role-aware list filtering

2026 additions:
  - ProductWishlistAdmin (read-only analytics view)
  - ProductCommissionSnapshotAdmin (immutable financial record)
  - Enhanced ProductAdmin with inline commission and inventory summary
  - ProductVariantAdmin standalone
"""
import logging

from django.contrib import admin
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from django.db.models import Sum, Count, Avg

# ── Canonical shared mixins (do NOT re-define locally) ──────────────────────
from apps.common.admin_mixins import SoftDeleteAdminMixin, ReadOnlyAdminMixin

from apps.product.models import (
    Product,
    ProductFaq,
    ProductReview,
    ProductWishlist,
    ProductInventoryLog,
    ProductTag,
    Coupon,
    DeliveryCourier,
    ProductCommissionSnapshot,
    # Phase 1 — 2026
    ProductFabricSpecification,
    ProductSizeAndMeasurementGuide,
    ProductShippingProfile,
    ProductPriceHistory,
    ProductViewLog,
    ProductVariantGalleryMedia,
)



# ─────────────────────────────────────────────────────────────────────────────
# INLINES
# ─────────────────────────────────────────────────────────────────────────────

class ProductVariantGalleryMediaInline(admin.TabularInline):
    """Inline manager for consolidated variant and gallery media rows."""

    model = ProductVariantGalleryMedia
    extra = 0
    fields = [
        "sku", "size", "color_name", "color_hex",
        "media", "media_preview", "media_type", "is_primary",
        "ordering", "alt_text", "barcode",
    ]
    readonly_fields = ["media_preview"]
    show_change_link = True

    def media_preview(self, obj):
        if obj.media:
            try:
                return format_html(
                    '<img src="{}" height="70" style="border-radius:6px;object-fit:cover;" />',
                    obj.media.url,
                )
            except Exception:
                return "—"
        return "—"
    media_preview.short_description = "Preview"


# ProductSpecification and ProductGalleryMedia are removed


class ProductFaqInline(admin.TabularInline):
    model = ProductFaq
    extra = 0
    fields = ["question", "answer"]


@admin.register(ProductFaq)
class ProductFaqAdmin(admin.ModelAdmin):
    list_display = ["product", "question", "created_at"]
    search_fields = ["product__title", "product__sku", "question", "answer"]
    list_select_related = ["product"]
    raw_id_fields = ["product"]
    ordering = ["product", "question"]


class InventoryLogReadOnlyInline(admin.TabularInline):
    """
    Read-only snapshot of the last 10 inventory events for a product.
    Full history accessible via ProductInventoryLogAdmin.
    """

    model = ProductInventoryLog
    extra = 0
    can_delete = False
    max_num = 10
    fields = [
        "quantity_delta", "quantity_before", "quantity_after",
        "reason", "reference_id", "created_at",
    ]
    readonly_fields = fields
    ordering = ["-created_at"]

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False


# ─────────────────────────────────────────────────────────────────────────────
# PRODUCT ADMIN
# ─────────────────────────────────────────────────────────────────────────────

@admin.register(Product)
class ProductAdmin(SoftDeleteAdminMixin, admin.ModelAdmin):
    """
    Enterprise product admin with:
      - Full fieldset organisation
      - Inline gallery, variants, specs, FAQs, inventory log
      - Bulk publish / archive / reject actions via service layer
      - Annotated metrics in list display
    """

    list_display = [
        "title", "vendor", "status", "soft_delete_badge", "price", "currency",
        "stock_qty", "in_stock", "featured", "rating", "review_count",
        "image_preview_small", "created_at",
    ]
    list_filter = [
        "status", "featured", "in_stock", "is_deleted",
        "categories",
    ]
    list_select_related = ["vendor"]
    search_fields = ["title", "slug", "sku", "vendor__business_name"]
    prepopulated_fields = {"slug": ("title",)}
    list_per_page = 25
    list_max_show_all = 200
    show_full_result_count = False
    readonly_fields = [
        "id", "sku", "views", "orders_count", "rating", "review_count",
        "created_at", "updated_at", "is_deleted", "deleted_at",
        "image_preview", "soft_delete_badge",
    ]
    fieldsets = (
        (_("Identity"), {
            "fields": ("id", "title", "slug", "sku", "description"),
        }),
        (_("Taxonomy"), {
            "fields": ("vendor", "categories", "sub_categories", "tags"),
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
            "fields": ("status", "featured", "hot_deal", "soft_delete_badge"),
        }),
        (_("Metrics"), {
            "fields": ("views", "orders_count", "rating", "review_count"),
        }),
        (_("SEO"), {
            "fields": ("meta_title", "meta_description"),
            "classes": ("collapse",),
        }),
        (_("Lifecycle"), {
            "fields": ("created_at", "updated_at", "is_deleted", "deleted_at"),
            "classes": ("collapse",),
        }),
    )
    filter_horizontal = ["tags"]
    inlines = [
        ProductVariantGalleryMediaInline,
        ProductFaqInline,
        InventoryLogReadOnlyInline,
    ]
    actions = [
        "publish_selected",
        "archive_selected",
        "reject_selected",
        "soft_delete_selected",
        "restore_selected",
    ]
    ordering = ["-created_at"]
    date_hierarchy = "created_at"
    show_full_result_count = False  # Performance: avoids COUNT(*) on large tables

    # ── Computed columns ───────────────────────────────────────────────────────

    def image_preview(self, obj):
        if obj.image:
            try:
                return format_html(
                    '<img src="{}" height="120" style="border-radius:8px;object-fit:cover;" />',
                    obj.image.url,
                )
            except Exception:
                return "—"
        return "—"
    image_preview.short_description = _("Cover Image Preview")

    def image_preview_small(self, obj):
        if obj.image:
            try:
                return format_html(
                    '<img src="{}" height="40" style="border-radius:4px;object-fit:cover;" />',
                    obj.image.url,
                )
            except Exception:
                return "—"
        return "—"
    image_preview_small.short_description = _("Cover")

    # ── Bulk actions via service layer ─────────────────────────────────────────

    @admin.action(description=_("✅ Publish selected products"))
    def publish_selected(self, request, queryset):
        from apps.product.services import approve_product
        count = 0
        for product in queryset:
            try:
                approve_product(product=product, actor=request.user)
                count += 1
            except Exception as exc:
                try:
                    self.message_user(
                        request,
                        f"Failed to publish '{product.title}': {exc}",
                        level="error",
                    )
                except Exception:
                    logger.warning("publish_selected: message_user unavailable — %s", exc)
        if count:
            try:
                self.message_user(request, f"✅ {count} product(s) published successfully.")
            except Exception:
                pass

    @admin.action(description=_("📦 Archive selected products"))
    def archive_selected(self, request, queryset):
        from apps.product.services import archive_product
        count = 0
        for product in queryset:
            try:
                archive_product(product=product, actor=request.user)
                count += 1
            except Exception as exc:
                self.message_user(request, f"Archive failed: {exc}", level="error")
        if count:
            self.message_user(request, f"📦 {count} product(s) archived.")

    @admin.action(description=_("❌ Reject selected products"))
    def reject_selected(self, request, queryset):
        from apps.product.services import reject_product
        count = 0
        for product in queryset:
            try:
                reject_product(product=product, actor=request.user)
                count += 1
            except Exception as exc:
                self.message_user(request, f"Reject failed: {exc}", level="error")
        if count:
            self.message_user(request, f"❌ {count} product(s) rejected.")

    @admin.action(description=_("🗑️ Soft-delete selected products"))
    def soft_delete_selected(self, request, queryset):
        count = 0
        for product in queryset:
            if hasattr(product, "soft_delete"):
                product.soft_delete()
                count += 1
        self.message_user(request, f"🗑️ {count} product(s) soft-deleted.")

    @admin.action(description=_("♻️ Restore soft-deleted products"))
    def restore_selected(self, request, queryset):
        count = 0
        for product in queryset:
            if hasattr(product, "restore"):
                product.restore()
                count += 1
        self.message_user(request, f"♻️ {count} product(s) restored.")


# ─────────────────────────────────────────────────────────────────────────────
# REVIEW ADMIN
# ─────────────────────────────────────────────────────────────────────────────

@admin.register(ProductReview)
class ProductReviewAdmin(admin.ModelAdmin):
    """
    Review moderation dashboard.
    Supports bulk moderate / deactivate / flag-vendor-reply actions.
    """

    list_display = [
        "product", "reviewer_name", "rating", "active",
        "moderated", "has_vendor_reply", "created_at",
    ]
    list_filter = ["active", "moderated", "rating"]
    search_fields = ["product__title", "reviewer_name", "reviewer_email", "review"]
    readonly_fields = ["created_at", "updated_at"]
    raw_id_fields = ["product"]
    list_select_related = ["product"]
    actions = ["moderate_selected", "deactivate_selected", "activate_selected"]
    date_hierarchy = "created_at"
    list_per_page = 25
    show_full_result_count = False

    def has_vendor_reply(self, obj):
        """Displays whether the vendor has replied."""
        reply = getattr(obj, "vendor_reply", None) or getattr(obj, "reply_text", None)
        if reply:
            return format_html('<span style="color:#22c55e">{}</span>', "✓ Yes")
        return format_html('<span style="color:#6b7280">{}</span>', "—")
    has_vendor_reply.short_description = "Vendor Reply"

    @admin.action(description="✅ Mark selected reviews as moderated")
    def moderate_selected(self, request, queryset):
        updated = queryset.update(moderated=True)
        self.message_user(request, f"✅ {updated} review(s) marked as moderated.")

    @admin.action(description="❌ Deactivate selected reviews")
    def deactivate_selected(self, request, queryset):
        updated = queryset.update(active=False)
        self.message_user(request, f"❌ {updated} review(s) deactivated.")

    @admin.action(description="✅ Activate selected reviews")
    def activate_selected(self, request, queryset):
        updated = queryset.update(active=True)
        self.message_user(request, f"✅ {updated} review(s) activated.")


# ─────────────────────────────────────────────────────────────────────────────
# COUPON ADMIN
# ─────────────────────────────────────────────────────────────────────────────

@admin.register(Coupon)
class CouponAdmin(admin.ModelAdmin):
    """Coupon / promotion code management."""

    list_display = [
        "code", "vendor", "discount_type", "discount_value",
        "usage_count", "usage_limit", "active", "valid_from", "valid_to",
        "utilisation_rate",
    ]
    list_filter = ["discount_type", "active"]
    search_fields = ["code", "vendor__business_name"]
    readonly_fields = ["usage_count", "created_at", "updated_at"]
    raw_id_fields = ["vendor"]
    date_hierarchy = "created_at"

    def utilisation_rate(self, obj):
        """Usage % relative to the coupon limit."""
        if obj.usage_limit and obj.usage_limit > 0:
            pct = round((obj.usage_count / obj.usage_limit) * 100)
            color = "#ef4444" if pct >= 90 else "#f59e0b" if pct >= 50 else "#22c55e"
            return format_html(
                '<span style="color:{}">{}/{} ({}%)</span>',
                color, obj.usage_count, obj.usage_limit, pct,
            )
        return f"{obj.usage_count} (unlimited)"
    utilisation_rate.short_description = "Utilisation"


# ─────────────────────────────────────────────────────────────────────────────
# DELIVERY COURIER ADMIN
# ─────────────────────────────────────────────────────────────────────────────

@admin.register(DeliveryCourier)
class DeliveryCourierAdmin(admin.ModelAdmin):
    """Shipping courier catalogue."""

    list_display = [
        "name", "base_fee", "estimated_days_min",
        "estimated_days_max", "active",
    ]
    list_filter = ["active"]
    search_fields = ["name"]


# ─────────────────────────────────────────────────────────────────────────────
# REFERENCE DATA ADMINS
# ─────────────────────────────────────────────────────────────────────────────

@admin.register(ProductTag)
class ProductTagAdmin(admin.ModelAdmin):
    list_display = ["name", "slug", "category"]
    prepopulated_fields = {"slug": ("name",)}
    search_fields = ["name"]
    list_filter = ["category"]





# ProductColor is removed


# ─────────────────────────────────────────────────────────────────────────────
# INVENTORY LOG ADMIN (READ-ONLY AUDIT)
# ─────────────────────────────────────────────────────────────────────────────

@admin.register(ProductInventoryLog)
class ProductInventoryLogAdmin(ReadOnlyAdminMixin, admin.ModelAdmin):
    """
    Immutable audit log for all inventory events.
    Read-only — add/change/delete are all forbidden.
    """

    list_display = [
        "product", "quantity_delta_display", "quantity_before",
        "quantity_after", "reason", "reference_id",
        "actor_display", "created_at",
    ]
    list_filter = ["reason"]
    search_fields = ["product__title", "reference_id"]
    readonly_fields = [f.name for f in ProductInventoryLog._meta.get_fields() if hasattr(f, "name")]
    date_hierarchy = "created_at"
    list_select_related = ["product"]
    ordering = ["-created_at"]

    def quantity_delta_display(self, obj):
        """Colour-codes the delta: green for positive, red for negative."""
        delta = obj.quantity_delta
        color = "#22c55e" if delta > 0 else "#ef4444"
        prefix = "+" if delta > 0 else ""
        return format_html(
            '<span style="color:{};font-weight:bold">{}{}</span>',
            color, prefix, delta,
        )
    quantity_delta_display.short_description = "Δ Qty"

    def actor_display(self, obj):
        """Shows actor email when available."""
        actor = getattr(obj, "actor", None) or getattr(obj, "created_by", None)
        if actor:
            return str(actor)
        return "—"
    actor_display.short_description = "Actor"


# ─────────────────────────────────────────────────────────────────────────────
# WISHLIST ADMIN (READ-ONLY ANALYTICS)
# ─────────────────────────────────────────────────────────────────────────────

@admin.register(ProductWishlist)
class ProductWishlistAdmin(ReadOnlyAdminMixin, admin.ModelAdmin):
    """
    Read-only analytics view of product wishlisting behaviour.
    Useful for merchandising decisions (most-wishlisted products).
    """

    list_display = ["product", "user", "created_at"]
    list_filter = []
    search_fields = ["product__title", "user__email"]
    readonly_fields = ["product", "user", "created_at"]
    list_select_related = ["product", "user"]
    date_hierarchy = "created_at"
    ordering = ["-created_at"]


# ─────────────────────────────────────────────────────────────────────────────
# COMMISSION SNAPSHOT ADMIN (READ-ONLY FINANCIAL RECORD)
# ─────────────────────────────────────────────────────────────────────────────

@admin.register(ProductCommissionSnapshot)
class ProductCommissionSnapshotAdmin(ReadOnlyAdminMixin, admin.ModelAdmin):
    """
    Immutable financial snapshot taken at order placement time.
    Preserves the commission_rate and sale_price at the exact moment of sale,
    even if the product is later repriced or deleted.
    """

    list_display = [
        "product", "commission_rate", "effective_from",
        "commission_amount_display", "created_at",
    ]
    search_fields = ["product__title", "product__sku"]
    readonly_fields = [
        f.name for f in ProductCommissionSnapshot._meta.get_fields()
        if hasattr(f, "name")
    ]
    list_select_related = ["product"]
    date_hierarchy = "created_at"
    ordering = ["-created_at"]

    def commission_amount_display(self, obj):
        """Displays effective_from → effective_to range for readability."""
        try:
            eff_from = obj.effective_from.strftime("%Y-%m-%d") if obj.effective_from else "—"
            eff_to = obj.effective_to.strftime("%Y-%m-%d") if obj.effective_to else "ongoing"
            return f"{eff_from} → {eff_to} @ {obj.commission_rate}%"
        except Exception:
            return "—"
    commission_amount_display.short_description = "Effective Period"


# ─────────────────────────────────────────────────────────────────────────────
# PHASE 1 ENTERPRISE MODEL ADMINS  (2026)
# ─────────────────────────────────────────────────────────────────────────────


@admin.register(ProductFabricSpecification)
class ProductFabricAdmin(admin.ModelAdmin):
    """
    Fabric composition record linked OneToOne to a Product.
    Full detail view with care instructions and organic/vegan flags.
    """

    list_display = [
        "product", "fabric_type", "care_instructions",
        "is_organic", "is_vegan", "country_of_origin",
    ]
    list_filter = ["care_instructions", "is_organic", "is_vegan"]
    search_fields = ["product__title", "fabric_type", "country_of_origin"]
    raw_id_fields = ["product"]
    readonly_fields = ["created_at", "updated_at"]
    fieldsets = (
        (_("Product"), {"fields": ("product",)}),
        (_("Fabric Details"), {"fields": (
            "fabric_type", "country_of_origin",
        )}),
        (_("Care"), {"fields": ("care_instructions",)}),
        (_("Sustainability"), {"fields": ("is_organic", "is_vegan")}),
        (_("Timestamps"), {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )


@admin.register(ProductSizeAndMeasurementGuide)
class ProductSizeAndMeasurementGuideAdmin(admin.ModelAdmin):
    """
    Reusable size-guide templates owned by vendors.
    Each row defines measurement ranges per size label.
    """

    list_display = [
        "name", "vendor", "size_label", "chest_cm",
        "waist_cm", "hip_cm", "sort_order",
    ]
    list_filter = ["size_label", "description"]
    search_fields = ["name", "vendor__store_name", "size_label"]
    raw_id_fields = ["vendor"]
    readonly_fields = ["created_at", "updated_at"]
    ordering = ["name", "sort_order"]


# @admin.register(ProductCertification)
# class ProductCertificationAdmin(admin.ModelAdmin):
#     """
#     Trust badges — sustainability, NAFDAC, SON, handmade, organic, fair trade.
#     Admin verifies certifications after document upload from vendor.
#     """

#     list_display = [
#         "product", "certification_type", "name",
#         "issuing_body", "is_verified", "valid_from", "valid_to",
#     ]
#     list_filter = ["certification_type", "is_verified"]
#     search_fields = ["product__title", "name", "issuing_body", "certificate_number"]
#     raw_id_fields = ["product"]
#     readonly_fields = ["created_at", "updated_at"]
#     actions = ["verify_selected", "unverify_selected"]

#     @admin.action(description="✅ Mark selected certifications as verified")
#     def verify_selected(self, request, queryset):
#         updated = queryset.update(is_verified=True)
#         self.message_user(request, f"✅ {updated} certification(s) verified.")

#     @admin.action(description="❌ Unverify selected certifications")
#     def unverify_selected(self, request, queryset):
#         updated = queryset.update(is_verified=False)
#         self.message_user(request, f"❌ {updated} certification(s) unverified.")

#     def badge_preview(self, obj):
#         if obj.badge_image:
#             try:
#                 return format_html(
#                     '<img src="{}" height="40" style="border-radius:4px;" />',
#                     obj.badge_image.url,
#                 )
#             except Exception:
#                 return "—"
#         return "—"
#     badge_preview.short_description = "Badge"


@admin.register(ProductShippingProfile)
class ProductShippingProfileAdmin(admin.ModelAdmin):
    """
    Per-product shipping configuration — overrides platform defaults.
    Critical for heavy fabrics (Aso-oke), fragile accessories, oversized items.
    """

    list_display = [
        "product", "weight_kg", "length_cm", "width_cm", "height_cm",
        "is_fragile", "requires_signature", "processing_days",
    ]
    list_filter = ["is_fragile", "requires_signature"]
    search_fields = ["product_shipping_profiles__title", "vendor__store_name"]
    raw_id_fields = ["vendor"]
    readonly_fields = ["created_at", "updated_at"]
    filter_horizontal = ["preferred_couriers"]
    fieldsets = (
        (_("Vendor"), {"fields": ("vendor",)}),
        (_("Dimensions"), {"fields": ("weight_kg", "length_cm", "width_cm", "height_cm")}),
        (_("Rules"), {"fields": (
            "is_fragile", "requires_signature", "processing_days",
            "free_shipping_threshold", "restricted_countries",
        )}),
        (_("Couriers"), {"fields": ("preferred_couriers",)}),
        (_("Timestamps"), {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )

    def product(self, obj):
        try:
            return getattr(obj, "product_shipping_profiles", None)
        except Exception:
            return None
    product.short_description = "Product"


@admin.register(ProductPriceHistory)
class ProductPriceHistoryAdmin(ReadOnlyAdminMixin, admin.ModelAdmin):
    """
    Append-only price change audit trail — IMMUTABLE.
    Used for price-drop alerts, analytics, and customer trust indicators.
    Admin cannot add, edit, or delete records here.
    """

    list_display = [
        "product", "old_price", "new_price", "currency",
        "change_reason", "changed_by", "created_at",
    ]
    list_filter = ["change_reason", "currency"]
    search_fields = ["product__title", "product__sku"]
    readonly_fields = [
        f.name for f in ProductPriceHistory._meta.get_fields()
        if hasattr(f, "name")
    ]
    list_select_related = ["product", "changed_by"]
    date_hierarchy = "created_at"
    ordering = ["-created_at"]
    list_per_page = 25
    show_full_result_count = False

    def price_change_display(self, obj):
        """Colour-codes price changes: green = drop, red = increase."""
        if obj.old_price is None:
            return format_html('<span style="color:#6b7280">{}</span>', "Initial listing")
        delta = obj.new_price - obj.old_price
        color = "#22c55e" if delta < 0 else "#ef4444"
        sign = "▼" if delta < 0 else "▲"
        return format_html(
            '<span style="color:{};font-weight:bold">{} {}</span>',
            color, sign, abs(delta),
        )
    price_change_display.short_description = "Δ Price"


@admin.register(ProductViewLog)
class ProductViewLogAdmin(ReadOnlyAdminMixin, admin.ModelAdmin):
    """
    Read-only analytics events from the AI recommendation engine.
    Each row = one PDP view (authenticated or anonymous).
    Used by data science team for collaborative filtering model training.
    NEVER editable — append-only analytics ledger.
    """

    list_display = [
        "product", "user", "session_key_short", "device_type",
        "duration_seconds", "referrer_display", "utm_source", "created_at",
    ]
    list_filter = ["device_type"]
    search_fields = ["product__title", "user__email", "session_key", "utm_campaign"]
    readonly_fields = [
        f.name for f in ProductViewLog._meta.get_fields()
        if hasattr(f, "name")
    ]
    list_select_related = ["product", "user"]
    date_hierarchy = "created_at"
    ordering = ["-created_at"]
    list_per_page = 25
    show_full_result_count = False  # Performance on high-volume analytics tables

    def session_key_short(self, obj):
        return obj.session_key[:10] + "…" if obj.session_key else "—"
    session_key_short.short_description = "Session"

    def referrer_display(self, obj):
        if obj.referrer_url:
            return format_html(
                '<a href="{}" target="_blank" title="{}">{}</a>',
                obj.referrer_url,
                obj.referrer_url,
                obj.referrer_url[:40] + ("…" if len(obj.referrer_url) > 40 else ""),
            )
        return "—"
    referrer_display.short_description = "Referrer"


# ─────────────────────────────────────────────────────────────────────────────
# EXPANDED SIZE ADMIN — now shows size_type taxonomy
# ─────────────────────────────────────────────────────────────────────────────




# ─────────────────────────────────────────────────────────────────────────────
# PRODUCT VARIANT GALLERY MEDIA — STANDALONE ADMIN
# ─────────────────────────────────────────────────────────────────────────────

@admin.register(ProductVariantGalleryMedia)
class ProductVariantGalleryMediaAdmin(SoftDeleteAdminMixin, admin.ModelAdmin):
    """
    Standalone admin for cross-product SKU and gallery media management.
    """

    list_display = [
        "sku", "product", "size", "color_name", "color_hex",
        "is_primary", "media_type", "media_preview", "soft_delete_badge",
    ]
    list_filter = ["is_primary", "media_type", "size"]
    search_fields = ["sku", "product__title", "product__sku", "barcode", "color_name"]
    list_select_related = ["product", "size"]
    raw_id_fields = ["product"]
    list_per_page = 25
    show_full_result_count = False
    readonly_fields = [
        "id", "sku", "media_preview", "created_at", "updated_at",
        "is_deleted", "deleted_at", "soft_delete_badge",
    ]
    ordering = ["product", "size", "color_name"]
    fieldsets = (
        (_("Identity"), {
            "fields": ("id", "sku", "barcode", "product"),
        }),
        (_("Variant Attributes"), {
            "fields": ("size", "color_name", "color_hex"),
        }),
        (_("Gallery / Media"), {
            "fields": ("media", "media_preview", "media_type", "alt_text", "ordering", "is_primary", "video_thumbnail", "duration_sec"),
        }),
        (_("Status"), {
            "fields": ("soft_delete_badge",),
        }),
        (_("Lifecycle"), {
            "fields": ("created_at", "updated_at", "is_deleted", "deleted_at"),
            "classes": ("collapse",),
        }),
    )
    empty_value_display = "-N/A-"

    def media_preview(self, obj):
        if obj.media:
            try:
                return format_html(
                    '<img src="{}" height="60" style="border-radius:6px;object-fit:cover;" />',
                    obj.media.url,
                )
            except Exception:
                return "—"
        return "—"
    media_preview.short_description = "Preview"


logger = logging.getLogger(__name__)
