# admin_backend/admin/category_admin.py
"""
Category Django Admin — Enterprise Edition.

Features:
  • AuditedModelAdmin  → every save/delete writes to AuditEventLog
  • CloudinaryUploadAdminMixin → admin image uploads go straight to Cloudinary
  • cloudinary_preview → renders the Cloudinary URL as an inline thumbnail
  • ImportExportModelAdmin → streaming export + idempotent import
"""

from django.contrib import admin
from django.utils.html import format_html
from apps.admin_backend.models import Category
from import_export.admin import ImportExportModelAdmin
from django import forms

from apps.audit_logs.mixins import AuditedModelAdmin
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
        fields = '__all__'

    def clean_name(self):
        name = self.cleaned_data['name']
        return name


class ActiveCategoryFilter(admin.SimpleListFilter):
    title = 'Active Categories'
    parameter_name = 'active_status'

    def lookups(self, request, model_admin):
        return (
            ('active', 'Active'),
            ('inactive', 'Inactive'),
        )

    def queryset(self, request, queryset):
        if self.value() == 'active':
            return queryset.filter(active=True)
        if self.value() == 'inactive':
            return queryset.filter(active=False)


@admin.register(Category)
class CategoryAdmin(AuditedModelAdmin, CloudinaryUploadAdminMixin, ImportExportModelAdmin):
    """
    Enterprise Category admin with Cloudinary upload + full audit logging.

    MRO: AuditedModelAdmin → CloudinaryUploadAdminMixin → ImportExportModelAdmin → ModelAdmin
    """

    # ── Cloudinary: map the 'image' form field to the category config ──────
    cloudinary_fields = {
        "image": ("fashionistar/categories/images", "category"),
    }

    form = CategoryAdminForm
    list_display = [
        'name',
        'cloudinary_preview',
        'active',
        'created_at',
        'updated_at',
        'slug',
    ]
    list_editable = ['active']
    search_fields = ['name', 'slug']
    prepopulated_fields = {"slug": ("name",)}
    list_filter = [ActiveCategoryFilter, 'created_at', 'updated_at']
    actions = [make_active, make_inactive]

    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'image', 'slug'),
        }),
        ('Cloudinary (auto-populated)', {
            'fields': ('cloudinary_preview', 'cloudinary_url'),
            'classes': ('collapse',),
            'description': (
                'cloudinary_url is populated automatically when you upload an image '
                'here OR when Cloudinary calls our webhook after a presign direct-upload.'
            ),
        }),
        ('Status', {
            'fields': ('active',),
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )

    readonly_fields = ('cloudinary_preview', 'cloudinary_url', 'created_at', 'updated_at')

    # ── Cloudinary URL inline preview ──────────────────────────────────────
    def cloudinary_preview(self, obj):
        """
        Render the Cloudinary URL as a thumbnail.
        Falls back to the legacy ``image`` field if cloudinary_url is empty.
        """
        url = obj.cloudinary_url or ""
        if not url and obj.image:
            try:
                url = obj.image.url
            except Exception:
                url = ""
        if url:
            return format_html(
                '<img src="{}" width="80" height="80" '
                'style="object-fit:cover; border-radius:6px; border:1px solid #ddd;" />',
                url,
            )
        return "—"

    cloudinary_preview.short_description = "Preview"
    cloudinary_preview.allow_tags = True
