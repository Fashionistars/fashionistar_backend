from django import forms
from django.contrib import admin
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from import_export.admin import ImportExportModelAdmin

from apps.audit_logs.mixins import AuditedModelAdmin
from apps.catalog.models import Collection
 



class CollectionAdminForm(forms.ModelForm):
    class Meta:
        model = Collection
        fields = "__all__"


@admin.register(Collection)
class CollectionAdmin(AuditedModelAdmin, ImportExportModelAdmin):
    form = CollectionAdminForm
    list_display = ["title", "sub_title", "cloudinary_preview", "slug", "created_at", "updated_at"]
    search_fields = ["title", "sub_title", "description", "slug"]
    prepopulated_fields = {"slug": ("title",)}
    list_filter = ["created_at", "updated_at"]
    readonly_fields = (
        "cloudinary_preview",
        "created_at",
        "updated_at",
    )

    fieldsets = (
        ("Basic Information", {"fields": ("title", "sub_title", "description", "slug")}),
        ("Images", {"fields": ("image", "background_image")}),
        (
            "Cloudinary Preview",
            {
                "fields": ("cloudinary_preview",),
                "classes": ("collapse",),
            },
        ),
        ("Timestamps", {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )

    def cloudinary_preview(self, obj):
        html_parts = []
        for img_field, title in (
            (obj.image, "Main image"),
            (obj.background_image, "Background image"),
        ):
            if img_field:
                try:
                    url = img_field.url
                    html_parts.append(
                        format_html(
                            '<img src="{}" width="80" height="80" '
                            'style="object-fit:cover; border-radius:6px; border:1px solid #ddd; margin-right:6px;" '
                            'title="{}" />',
                            url,
                            title,
                        )
                    )
                except Exception:
                    pass
        if html_parts:
            return mark_safe("".join(str(part) for part in html_parts))
        return "-"

    cloudinary_preview.short_description = "Preview"
