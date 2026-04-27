from django.contrib import admin
from django.utils.html import format_html
from import_export.admin import ImportExportModelAdmin

from apps.audit_logs.mixins import AuditedModelAdmin
from apps.catalog.models import BlogMedia, BlogPost


class BlogMediaInline(admin.TabularInline):
    model = BlogMedia
    extra = 0
    fields = ("image", "alt_text", "sort_order")
    readonly_fields = ()


@admin.register(BlogPost)
class BlogPostAdmin(AuditedModelAdmin, ImportExportModelAdmin):
    list_display = [
        "title",
        "status",
        "is_featured",
        "blog_preview",
        "published_at",
        "created_at",
        "updated_at",
    ]
    search_fields = ["title", "slug", "excerpt", "content", "seo_title", "seo_description"]
    list_filter = ["status", "is_featured", "published_at", "created_at", "updated_at"]
    prepopulated_fields = {"slug": ("title",)}
    readonly_fields = ("blog_preview", "view_count", "created_at", "updated_at")
    inlines = [BlogMediaInline]

    fieldsets = (
        ("Editorial", {"fields": ("title", "slug", "author", "category", "excerpt", "content")}),
        (
            "Publishing",
            {"fields": ("status", "is_featured", "published_at", "tags")},
        ),
        (
            "SEO",
            {"fields": ("seo_title", "seo_description")},
        ),
        (
            "Media",
            {
                "fields": (
                    "featured_image",
                    "blog_preview",
                )
            },
        ),
        ("Metrics", {"fields": ("view_count", "created_at", "updated_at"), "classes": ("collapse",)}),
    )

    def blog_preview(self, obj):
        url = obj.image_url
        if not url:
            return "-"
        return format_html(
            '<img src="{}" width="96" height="64" '
            'style="object-fit:cover; border-radius:6px; border:1px solid #ddd;" />',
            url,
        )

    blog_preview.short_description = "Preview"


@admin.register(BlogMedia)
class BlogMediaAdmin(AuditedModelAdmin, ImportExportModelAdmin):
    list_display = ["post", "alt_text", "sort_order", "created_at"]
    search_fields = ["post__title", "alt_text", "public_id"]
    list_filter = ["created_at", "updated_at"]
