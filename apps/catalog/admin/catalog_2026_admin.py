# apps/catalog/admin/catalog_2026_admin.py
"""
Admin registrations for Phase 2 (2026) catalog models:
  FashionStyleGuide, Lookbook / LookbookItem,
  FashionTrend, TrendingProduct,
  SizeChart / SizeRecommendation, Fabric.

All classes follow the existing catalog admin conventions:
  - AuditedModelAdmin base for immutable change tracking.
  - CloudinaryUploadAdminMixin for two-phase media upload.
  - list_display + search_fields + list_filter + readonly_fields.
  - Inlines for child models where parent-child relationship exists.
"""

from django.contrib import admin
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from apps.audit_logs.mixins import AuditedModelAdmin
from apps.catalog.models import (
    Fabric,
    FashionStyleGuide,
    FashionTrend,
    Lookbook,
    LookbookItem,
    SizeChart,
    SizeRecommendation,
    TrendingProduct,
)
from apps.common.admin_cloudinary_mixin import CloudinaryUploadAdminMixin


# ─────────────────────────────────────────────────────────────────────────────
# FASHION STYLE GUIDE
# ─────────────────────────────────────────────────────────────────────────────


@admin.register(FashionStyleGuide)
class FashionStyleGuideAdmin(AuditedModelAdmin, CloudinaryUploadAdminMixin, admin.ModelAdmin):
    """Admin for FashionStyleGuide — editorial + AI-curated style guides."""

    cloudinary_fields = {
        "cover_image": ("fashionistar/catalog/style-guides", "style_guide"),
    }

    list_display = [
        "title",
        "cover_image_preview",
        "season",
        "year",
        "is_published",
        "ai_generated",
        "view_count",
        "published_at",
        "created_at",
    ]
    list_filter = ["is_published", "ai_generated", "season", "year"]
    list_editable = ["is_published"]
    search_fields = ["title", "slug", "seo_title"]
    prepopulated_fields = {"slug": ("title",)}
    readonly_fields = ["cover_image_preview", "view_count", "share_count", "created_at", "updated_at"]
    filter_horizontal = ["trend_tags", "featured_products"]

    fieldsets = (
        (_("Content"), {"fields": ("title", "slug", "description", "cover_image", "cover_image_preview")}),
        (_("Season & Year"), {"fields": ("season", "year")}),
        (_("Publishing"), {"fields": ("is_published", "published_at")}),
        (_("AI"), {"fields": ("ai_generated", "ai_prompt_used"), "classes": ("collapse",)}),
        (_("SEO"), {"fields": ("seo_title", "seo_description"), "classes": ("collapse",)}),
        (_("Engagement"), {"fields": ("view_count", "share_count"), "classes": ("collapse",)}),
        (_("Relations"), {"fields": ("editor", "trend_tags", "featured_products"), "classes": ("collapse",)}),
        (_("Timestamps"), {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )

    def cover_image_preview(self, obj):
        if not obj.cover_image:
            return "—"
        try:
            url = obj.cover_image.url
        except Exception:
            return "—"
        return format_html(
            '<img src="{}" width="100" height="70" '
            'style="object-fit:cover; border-radius:6px; border:1px solid #ddd;" />',
            url,
        )

    cover_image_preview.short_description = _("Preview")


# ─────────────────────────────────────────────────────────────────────────────
# LOOKBOOK + LOOKBOOK ITEM (inline)
# ─────────────────────────────────────────────────────────────────────────────


class LookbookItemInline(admin.TabularInline):
    """Inline for editing LookbookItems within a Lookbook."""

    model = LookbookItem
    extra = 0
    fields = ["product", "sort_order", "annotation_text", "position_x", "position_y"]
    ordering = ["sort_order"]
    autocomplete_fields = ["product"]


@admin.register(Lookbook)
class LookbookAdmin(AuditedModelAdmin, CloudinaryUploadAdminMixin, admin.ModelAdmin):
    """Admin for Lookbook — vendor or editorial curated image collections."""

    cloudinary_fields = {
        "cover_image": ("fashionistar/catalog/lookbooks", "lookbook"),
    }
    inlines = [LookbookItemInline]

    list_display = [
        "title",
        "cover_image_preview",
        "vendor",
        "is_published",
        "likes_count",
        "views_count",
        "published_at",
        "featured_until",
    ]
    list_filter = ["is_published", "published_at"]
    list_editable = ["is_published"]
    search_fields = ["title", "slug", "vendor__business_name"]
    prepopulated_fields = {"slug": ("title",)}
    readonly_fields = ["cover_image_preview", "likes_count", "views_count", "created_at", "updated_at"]

    fieldsets = (
        (_("Content"), {"fields": ("title", "slug", "description", "cover_image", "cover_image_preview")}),
        (_("Owner"), {"fields": ("vendor", "style_guide")}),
        (_("Publishing"), {"fields": ("is_published", "published_at", "featured_until")}),
        (_("Engagement"), {"fields": ("likes_count", "views_count"), "classes": ("collapse",)}),
        (_("Gallery"), {"fields": ("gallery_images",), "classes": ("collapse",)}),
        (_("Timestamps"), {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )

    def cover_image_preview(self, obj):
        if not obj.cover_image:
            return "—"
        try:
            url = obj.cover_image.url
        except Exception:
            return "—"
        return format_html(
            '<img src="{}" width="100" height="70" '
            'style="object-fit:cover; border-radius:6px; border:1px solid #ddd;" />',
            url,
        )

    cover_image_preview.short_description = _("Preview")


@admin.register(LookbookItem)
class LookbookItemAdmin(AuditedModelAdmin, admin.ModelAdmin):
    """Standalone admin for LookbookItem (used for bulk operations)."""

    list_display = ["lookbook", "product", "sort_order", "annotation_text"]
    list_filter = ["lookbook"]
    search_fields = ["lookbook__title", "product__title", "annotation_text"]
    autocomplete_fields = ["product", "lookbook"]


# ─────────────────────────────────────────────────────────────────────────────
# FASHION TREND
# ─────────────────────────────────────────────────────────────────────────────


@admin.register(FashionTrend)
class FashionTrendAdmin(AuditedModelAdmin, CloudinaryUploadAdminMixin, admin.ModelAdmin):
    """Admin for FashionTrend — platform-level trend signals."""

    cloudinary_fields = {
        "cover_image": ("fashionistar/catalog/trends", "trend"),
    }

    list_display = [
        "name",
        "cover_image_preview",
        "trend_type",
        "trend_score",
        "is_active",
        "origin_country",
        "origin_city",
        "created_at",
    ]
    list_filter = ["trend_type", "is_active"]
    list_editable = ["is_active", "trend_score"]
    search_fields = ["name", "slug", "origin_country", "origin_city"]
    prepopulated_fields = {"slug": ("name",)}
    readonly_fields = ["cover_image_preview", "created_at", "updated_at"]
    filter_horizontal = ["associated_tags", "associated_categories"]

    fieldsets = (
        (_("Content"), {"fields": ("name", "slug", "description", "cover_image", "cover_image_preview")}),
        (_("Trend Data"), {"fields": ("trend_type", "trend_score", "is_active", "featured_until")}),
        (_("Origin"), {"fields": ("origin_country", "origin_city")}),
        (_("Relations"), {"fields": ("associated_tags", "associated_categories"), "classes": ("collapse",)}),
        (_("AI"), {"fields": ("embedding_vector",), "classes": ("collapse",)}),
        (_("Timestamps"), {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )

    def cover_image_preview(self, obj):
        if not obj.cover_image:
            return "—"
        try:
            url = obj.cover_image.url
        except Exception:
            return "—"
        return format_html(
            '<img src="{}" width="100" height="70" '
            'style="object-fit:cover; border-radius:6px; border:1px solid #ddd;" />',
            url,
        )

    cover_image_preview.short_description = _("Preview")


# ─────────────────────────────────────────────────────────────────────────────
# TRENDING PRODUCT (read-only materialized view admin)
# ─────────────────────────────────────────────────────────────────────────────


@admin.register(TrendingProduct)
class TrendingProductAdmin(admin.ModelAdmin):
    """
    Read-only admin for TrendingProduct materialized view.
    Refreshed by Celery beat — no manual edits permitted.
    """

    list_display = ["product", "period", "rank", "trend_score", "refreshed_at"]
    list_filter = ["period"]
    search_fields = ["product__title"]
    readonly_fields = ["product", "period", "rank", "trend_score", "refreshed_at", "created_at", "updated_at"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser


# ─────────────────────────────────────────────────────────────────────────────
# SIZE CHART + SIZE RECOMMENDATION
# ─────────────────────────────────────────────────────────────────────────────


@admin.register(SizeChart)
class SizeChartAdmin(AuditedModelAdmin, admin.ModelAdmin):
    """Admin for SizeChart — reusable category/brand size matrices."""

    list_display = ["name", "gender", "size_type", "category", "brand", "unit", "is_active", "sort_order"]
    list_filter = ["gender", "size_type", "is_active", "unit"]
    list_editable = ["is_active", "sort_order"]
    search_fields = ["name", "slug", "category__name", "brand__name"]
    prepopulated_fields = {"slug": ("name",)}
    readonly_fields = ["created_at", "updated_at"]

    fieldsets = (
        (_("Identity"), {"fields": ("name", "slug")}),
        (_("Classification"), {"fields": ("gender", "size_type", "unit", "is_active", "sort_order")}),
        (_("Relations"), {"fields": ("category", "brand")}),
        (_("Chart Data"), {"fields": ("chart_data",)}),
        (_("Timestamps"), {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )


@admin.register(SizeRecommendation)
class SizeRecommendationAdmin(AuditedModelAdmin, admin.ModelAdmin):
    """Admin for SizeRecommendation — AI-generated size picks."""

    list_display = [
        "measurement_profile",
        "size_chart",
        "recommended_size",
        "confidence_score",
        "model_version",
        "generated_at",
    ]
    list_filter = ["recommended_size", "model_version"]
    search_fields = ["measurement_profile__id", "size_chart__name", "recommended_size"]
    readonly_fields = ["generated_at", "created_at", "updated_at"]

    def has_add_permission(self, request):
        return False  # Created only by AI service layer


# ─────────────────────────────────────────────────────────────────────────────
# FABRIC
# ─────────────────────────────────────────────────────────────────────────────


@admin.register(Fabric)
class FabricAdmin(AuditedModelAdmin, CloudinaryUploadAdminMixin, admin.ModelAdmin):
    """Admin for Fabric — material + care instruction + sustainability data."""

    cloudinary_fields = {
        "texture_image": ("fashionistar/catalog/fabrics", "fabric"),
    }

    list_display = [
        "name",
        "texture_preview",
        "sustainability_score",
        "origin_country",
        "is_active",
        "created_at",
    ]
    list_filter = ["is_active", "origin_country"]
    list_editable = ["is_active"]
    search_fields = ["name", "slug", "origin_country"]
    prepopulated_fields = {"slug": ("name",)}
    readonly_fields = ["texture_preview", "created_at", "updated_at"]

    fieldsets = (
        (_("Identity"), {"fields": ("name", "slug", "description")}),
        (_("Material"), {"fields": ("composition", "care_instructions", "properties")}),
        (_("Media"), {"fields": ("texture_image", "texture_preview")}),
        (_("Sustainability"), {"fields": ("sustainability_score", "origin_country")}),
        (_("Status"), {"fields": ("is_active",)}),
        (_("Timestamps"), {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )

    def texture_preview(self, obj):
        if not obj.texture_image:
            return "—"
        try:
            url = obj.texture_image.url
        except Exception:
            return "—"
        return format_html(
            '<img src="{}" width="80" height="80" '
            'style="object-fit:cover; border-radius:6px; border:1px solid #ddd;" />',
            url,
        )

    texture_preview.short_description = _("Texture Preview")
