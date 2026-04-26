from django import forms
from django.contrib import admin
from django.utils.html import format_html
from import_export.admin import ImportExportModelAdmin

from apps.audit_logs.mixins import AuditedModelAdmin
from apps.catalog.models import Category
from apps.common.admin_cloudinary_mixin import CloudinaryUploadAdminMixin


@admin.action(description="Mark selected categories as active")
def make_active(modeladmin, request, queryset):
    queryset.update(active=True)


@admin.action(description="Mark selected categories as inactive")
def make_inactive(modeladmin, request, queryset):
    queryset.update(active=False)


class CategoryAdminForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = "__all__"

    def clean_name(self):
        return self.cleaned_data["name"].strip()


class ActiveCategoryFilter(admin.SimpleListFilter):
    title = "Active Categories"
    parameter_name = "active_status"

    def lookups(self, request, model_admin):
        return (("active", "Active"), ("inactive", "Inactive"))

    def queryset(self, request, queryset):
        if self.value() == "active":
            return queryset.filter(active=True)
        if self.value() == "inactive":
            return queryset.filter(active=False)
        return queryset


@admin.register(Category)
class CategoryAdmin(AuditedModelAdmin, CloudinaryUploadAdminMixin, ImportExportModelAdmin):
    cloudinary_fields = {"image": ("fashionistar/categories/images", "category")}
    form = CategoryAdminForm
    list_display = ["name", "cloudinary_preview", "active", "created_at", "updated_at", "slug"]
    list_editable = ["active"]
    search_fields = ["name", "slug"]
    prepopulated_fields = {"slug": ("name",)}
    list_filter = [ActiveCategoryFilter, "created_at", "updated_at"]
    actions = [make_active, make_inactive]
    readonly_fields = ("cloudinary_preview", "cloudinary_url", "created_at", "updated_at")

    fieldsets = (
        ("Basic Information", {"fields": ("name", "image", "slug")}),
        (
            "Cloudinary",
            {
                "fields": ("cloudinary_preview", "cloudinary_url"),
                "classes": ("collapse",),
            },
        ),
        ("Status", {"fields": ("active",)}),
        ("Timestamps", {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )

    def cloudinary_preview(self, obj):
        url = obj.cloudinary_url or ""
        if not url and obj.image:
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
