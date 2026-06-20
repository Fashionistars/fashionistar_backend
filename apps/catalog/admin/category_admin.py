from django import forms
from django.contrib import admin
from django.utils.html import format_html
from import_export.admin import ImportExportModelAdmin

from apps.audit_logs.mixins import AuditedModelAdmin
from apps.catalog.models import Category
from apps.common.admin_cloudinary_mixin import CloudinaryUploadAdminMixin


from django.utils import timezone

@admin.action(description="Soft-delete selected categories")
def soft_delete_selected(modeladmin, request, queryset):
    queryset.update(is_deleted=True, deleted_at=timezone.now())


@admin.action(description="Restore selected categories")
def restore_selected(modeladmin, request, queryset):
    queryset.update(is_deleted=False, deleted_at=None)


class CategoryAdminForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = "__all__"

    def clean_name(self):
        return self.cleaned_data["name"].strip()


@admin.register(Category)
class CategoryAdmin(
    AuditedModelAdmin, CloudinaryUploadAdminMixin, ImportExportModelAdmin
):
    cloudinary_fields = {"image": ("fashionistar/categories/images", "category")}
    form = CategoryAdminForm
    list_display = [
        "name",
        "cloudinary_preview",
        "is_deleted",
        "created_at",
        "updated_at",
        "slug",
    ]
    search_fields = ["name", "slug"]
    prepopulated_fields = {"slug": ("name",)}
    list_filter = ["is_deleted", "created_at", "updated_at"]
    actions = [soft_delete_selected, restore_selected]
    readonly_fields = ("cloudinary_preview", "is_deleted", "created_at", "updated_at")

    def save_model(self, request, obj, form, change):
        if not obj.user:
            obj.user = request.user
        super().save_model(request, obj, form, change)

    fieldsets = (
        ("Basic Information", {"fields": ("name", "image", "slug")}),
        (
            "Cloudinary Preview",
            {
                "fields": ("cloudinary_preview",),
                "classes": ("collapse",),
            },
        ),
        ("Status", {"fields": ("is_deleted",)}),
        (
            "Timestamps",
            {"fields": ("created_at", "updated_at"), "classes": ("collapse",)},
        ),
    )

    def cloudinary_preview(self, obj):
        if not obj.image:
            return "-"
        try:
            url = obj.image.url
        except Exception:
            url = ""
        if not url:
            return "-"
        return format_html(
            '<img src="{}" width="80" height="80" '
            'style="object-fit:cover; border-radius:6px; border:1px solid #ddd;" />',
            url,
        )

    cloudinary_preview.short_description = "Preview"
