# admin_backend/admin/collection_admin.py
"""
Collections Django Admin — Enterprise Edition.

Features:
  • AuditedModelAdmin  → every save/delete writes to AuditEventLog
  • CloudinaryUploadAdminMixin → admin image uploads go straight to Cloudinary
  • cloudinary_preview → renders cloudinary_url / background_cloudinary_url as thumbnails
  • ImportExportModelAdmin → streaming export + idempotent import
"""

from django.contrib import admin
from django.utils.html import format_html
from admin_backend.models import Collections
from import_export.admin import ImportExportModelAdmin
from django import forms

from apps.audit_logs.mixins import AuditedModelAdmin
from apps.common.admin_cloudinary_mixin import CloudinaryUploadAdminMixin


class CollectionsAdminForm(forms.ModelForm):
    class Meta:
        model = Collections
        fields = '__all__'


@admin.register(Collections)
class CollectionsAdmin(AuditedModelAdmin, CloudinaryUploadAdminMixin, ImportExportModelAdmin):
    """
    Enterprise Collections admin with Cloudinary upload + full audit logging.

    MRO: AuditedModelAdmin → CloudinaryUploadAdminMixin → ImportExportModelAdmin → ModelAdmin

    Two Cloudinary fields:
      - image            → fashionistar/collections/images  (hero / product)
      - background_image → fashionistar/collections/images  (banner/background)

    Both are uploaded to Cloudinary via CloudinaryUploadAdminMixin.save_model()
    and their secure_url is stored in cloudinary_url / background_cloudinary_url.
    """

    # ── Cloudinary: map both image fields ────────────────────────────────────
    cloudinary_fields = {
        "image":            ("fashionistar/collections/images", "collection"),
        "background_image": ("fashionistar/collections/images", "collection"),
    }

    form = CollectionsAdminForm
    list_display = [
        'title',
        'sub_title',
        'cloudinary_preview',
        'slug',
        'created_at',
        'updated_at',
    ]
    search_fields = ['title', 'sub_title', 'description', 'slug']
    prepopulated_fields = {"slug": ("title",)}
    list_filter = ['created_at', 'updated_at']

    fieldsets = (
        ('Basic Information', {
            'fields': ('title', 'sub_title', 'description', 'slug'),
        }),
        ('Images (Upload here or leave for webhook)', {
            'fields': (
                'image',
                'background_image',
            ),
            'description': (
                'Upload images here and they will be sent directly to Cloudinary. '
                'You can also use the presign API — after upload the Cloudinary webhook '
                'auto-populates cloudinary_url and background_cloudinary_url.'
            ),
        }),
        ('Cloudinary URLs (auto-populated)', {
            'fields': (
                'cloudinary_preview',
                'cloudinary_url',
                'background_cloudinary_url',
            ),
            'classes': ('collapse',),
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )

    readonly_fields = (
        'cloudinary_preview',
        'cloudinary_url',
        'background_cloudinary_url',
        'created_at',
        'updated_at',
    )

    # ── Cloudinary URL inline preview ──────────────────────────────────────
    def cloudinary_preview(self, obj):
        """
        Render both Cloudinary URLs (main + background) as thumbnails.
        Falls back to legacy ImageField URLs if Cloudinary URLs are empty.
        """
        html_parts = []

        # Main image
        url = obj.cloudinary_url or ""
        if not url and obj.image:
            try:
                url = obj.image.url
            except Exception:
                url = ""
        if url:
            html_parts.append(format_html(
                '<img src="{}" width="80" height="80" '
                'style="object-fit:cover; border-radius:6px; border:1px solid #ddd; margin-right:6px;" '
                'title="Main image" />',
                url,
            ))

        # Background image
        bg_url = obj.background_cloudinary_url or ""
        if not bg_url and obj.background_image:
            try:
                bg_url = obj.background_image.url
            except Exception:
                bg_url = ""
        if bg_url:
            html_parts.append(format_html(
                '<img src="{}" width="80" height="80" '
                'style="object-fit:cover; border-radius:6px; border:1px solid #ddd;" '
                'title="Background image" />',
                bg_url,
            ))

        if html_parts:
            from django.utils.safestring import mark_safe
            return mark_safe("".join(str(p) for p in html_parts))
        return "—"

    cloudinary_preview.short_description = "Preview"
    cloudinary_preview.allow_tags = True