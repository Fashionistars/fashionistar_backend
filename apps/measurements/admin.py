# apps/measurements/admin.py
"""
Django Admin for the Measurements domain.

Models registered:
  - MeasurementProfile : Client body measurement set with admin verification

Production rules:
  - Financial/personal data displayed with appropriate care
  - Verification action gated to staff only
  - Reference photo rendered as Cloudinary thumbnail in list + changeform
  - Body measurements displayed in a dedicated "Body Map" fieldset
  - Admin can mark profiles as verified (acts as tailor validation stamp)

2026 features:
  - Compact "Body Map" fieldset grouping all measurements visually
  - Verified/unverified badge in list view
  - Bulk verify action for staff
  - Image thumbnail preview for reference_photo
"""
import logging

from django.contrib import admin
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from django.contrib import messages

from apps.measurements.models import MeasurementProfile

logger = logging.getLogger(__name__)


@admin.register(MeasurementProfile)
class MeasurementProfileAdmin(admin.ModelAdmin):
    """
    Admin for MeasurementProfile — the client body measurement data store.

    The "Body Map" fieldset groups all measurement fields in tailoring order:
    Torso → Lower Body → Arms → Full Body.

    Admin staff can verify measurement profiles via the bulk action.
    """

    list_display = [
        "owner", "name", "is_default", "verified_badge",
        "core_measurements_display", "unit", "reference_photo_thumb",
        "updated_at",
    ]
    list_filter = ["is_verified", "is_default", "unit"]
    search_fields = ["owner__email", "name", "notes"]
    ordering = ["-updated_at"]
    date_hierarchy = "updated_at"
    list_select_related = ["owner", "verified_by"]
    raw_id_fields = ["owner", "verified_by"]
    list_per_page = 25
    list_max_show_all = 200
    show_full_result_count = False
    empty_value_display = "-N/A-"

    readonly_fields = [
        "created_at", "updated_at",
        "verified_badge", "reference_photo_thumb",
        "core_measurements_display",
    ]

    fieldsets = (
        (_("Identity"), {
            "fields": ("owner", "name", "is_default", "unit"),
        }),
        (_("📐 Body Map — Torso"), {
            "fields": (
                "bust", "waist", "hips",
                "shoulder_width", "neck",
            ),
        }),
        (_("📐 Body Map — Lower Body"), {
            "fields": (
                "inseam", "thigh", "knee", "ankle",
            ),
        }),
        (_("📐 Body Map — Arms"), {
            "fields": (
                "arm_length", "bicep", "wrist",
            ),
        }),
        (_("📐 Body Map — Full Body"), {
            "fields": ("height", "weight_kg"),
        }),
        (_("Reference Photo"), {
            "fields": ("reference_photo", "reference_photo_thumb"),
        }),
        (_("Verification"), {
            "fields": (
                "is_verified", "verified_by", "verified_badge", "notes",
            ),
        }),
        (_("Timestamps"), {
            "fields": ("created_at", "updated_at"),
            "classes": ("collapse",),
        }),
    )

    actions = ["action_verify_profiles", "action_unverify_profiles"]

    # ── List display helpers ─────────────────────────────────────────────────

    @admin.display(description="Verified", boolean=False)
    def verified_badge(self, obj):
        if obj.is_verified:
            return format_html(
                '<span style="background:#dcfce7;color:#166534;padding:2px 8px;'
                'border-radius:20px;font-size:11px;font-weight:600">✓ Verified</span>'
            )
        return format_html(
            '<span style="background:#fef3c7;color:#92400e;padding:2px 8px;'
            'border-radius:20px;font-size:11px;font-weight:600">⏳ Pending</span>'
        )

    @admin.display(description="Core Measurements")
    def core_measurements_display(self, obj):
        """Compact bust / waist / hips / height summary."""
        parts = []
        if obj.bust:
            parts.append(f"B:{obj.bust}{obj.unit}")
        if obj.waist:
            parts.append(f"W:{obj.waist}{obj.unit}")
        if obj.hips:
            parts.append(f"H:{obj.hips}{obj.unit}")
        if obj.height:
            parts.append(f"↕{obj.height}{obj.unit}")
        return " · ".join(parts) if parts else "—"

    @admin.display(description="Photo")
    def reference_photo_thumb(self, obj):
        url = None
        if obj.reference_photo:
            # Cloudinary field returns the URL via .url
            try:
                url = obj.reference_photo.url
            except Exception:
                pass
        if url:
            return format_html(
                '<img src="{}" height="50" style="border-radius:6px;'
                'object-fit:cover;border:1px solid #e2e8f0;" />',
                url,
            )
        return "—"

    # ── Admin actions ────────────────────────────────────────────────────────

    @admin.action(description="✓ Mark selected profiles as Verified")
    def action_verify_profiles(self, request, queryset):
        if not request.user.is_staff:
            self.message_user(request, "Permission denied.", level=messages.ERROR)
            return
        updated = queryset.filter(is_verified=False).update(
            is_verified=True,
            verified_by=request.user,
        )
        self.message_user(
            request,
            f"✅ {updated} measurement profile(s) marked as verified.",
            level=messages.SUCCESS,
        )

    @admin.action(description="✗ Remove verification from selected profiles")
    def action_unverify_profiles(self, request, queryset):
        if not request.user.is_superuser:
            self.message_user(request, "Superuser only.", level=messages.ERROR)
            return
        updated = queryset.filter(is_verified=True).update(
            is_verified=False,
            verified_by=None,
        )
        self.message_user(
            request,
            f"↩️ {updated} profile(s) un-verified.",
            level=messages.WARNING,
        )
