# apps/measurements/admin.py
"""
Django Admin registration for the Measurements domain.
"""
from django.contrib import admin
from apps.measurements.models import MeasurementProfile


@admin.register(MeasurementProfile)
class MeasurementProfileAdmin(admin.ModelAdmin):
    list_display = (
        "id", "owner", "name", "is_default", "is_verified",
        "has_core_measurements_display", "updated_at",
    )
    list_filter  = ("is_default", "is_verified", "unit")
    search_fields = ("owner__email", "name")
    readonly_fields = (
        "owner", "created_at", "updated_at",
        "verified_by", "has_core_measurements_display",
    )
    fieldsets = (
        ("Profile", {
            "fields": ("owner", "name", "is_default", "unit", "notes", "is_verified", "verified_by"),
        }),
        ("Torso", {
            "fields": ("bust", "waist", "hips", "shoulder_width", "neck"),
        }),
        ("Lower Body", {
            "fields": ("inseam", "thigh", "knee", "ankle"),
        }),
        ("Arms", {
            "fields": ("arm_length", "bicep", "wrist"),
        }),
        ("Full Body", {
            "fields": ("height", "weight_kg"),
        }),
        ("Media", {
            "fields": ("reference_photo",),
        }),
        ("Timestamps", {
            "fields": ("created_at", "updated_at"),
        }),
    )

    @admin.display(description="Core Measurements?", boolean=True)
    def has_core_measurements_display(self, obj):
        return obj.has_core_measurements
