# apps/measurements/serializers/measurement_serializers.py
"""
DRF serializers for the Measurements domain.
"""
from rest_framework import serializers
from apps.measurements.models import MeasurementProfile, MeasurementUnit


class MeasurementProfileSerializer(serializers.ModelSerializer):
    """Read serializer for a MeasurementProfile."""

    has_core_measurements = serializers.BooleanField(read_only=True)
    owner_email = serializers.EmailField(source="owner.email", read_only=True)
    reference_photo_url = serializers.SerializerMethodField()

    class Meta:
        model = MeasurementProfile
        fields = [
            "id",
            "name",
            "is_default",
            "unit",
            "has_core_measurements",
            "is_verified",
            "owner_email",
            # Torso
            "bust",
            "waist",
            "hips",
            "shoulder_width",
            "neck",
            # Lower body
            "inseam",
            "thigh",
            "knee",
            "ankle",
            # Arms
            "arm_length",
            "bicep",
            "wrist",
            # Full body
            "height",
            "weight_kg",
            # Media
            "reference_photo_url",
            # Notes
            "notes",
            # Timestamps
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def get_reference_photo_url(self, obj) -> str | None:
        if obj.reference_photo:
            return obj.reference_photo.url
        return None


# ─────────────────────────────────────────────────────────────────────────────
# WRITE SERIALIZER
# ─────────────────────────────────────────────────────────────────────────────

_MEASUREMENT_FIELDS = [
    "bust", "waist", "hips", "shoulder_width", "neck",
    "inseam", "thigh", "knee", "ankle",
    "arm_length", "bicep", "wrist",
    "height", "weight_kg",
]


class MeasurementProfileWriteSerializer(serializers.Serializer):
    """
    Write serializer for creating or updating a MeasurementProfile.
    Owner is injected from the request context — never from payload.
    """

    name = serializers.CharField(max_length=100, default="My Measurements")
    unit = serializers.ChoiceField(choices=MeasurementUnit.choices, default=MeasurementUnit.CM)
    notes = serializers.CharField(allow_blank=True, required=False, default="")
    set_as_default = serializers.BooleanField(required=False, default=False)

    # Measurement fields — all optional
    bust           = serializers.DecimalField(max_digits=6, decimal_places=2, required=False, allow_null=True)
    waist          = serializers.DecimalField(max_digits=6, decimal_places=2, required=False, allow_null=True)
    hips           = serializers.DecimalField(max_digits=6, decimal_places=2, required=False, allow_null=True)
    shoulder_width = serializers.DecimalField(max_digits=6, decimal_places=2, required=False, allow_null=True)
    neck           = serializers.DecimalField(max_digits=6, decimal_places=2, required=False, allow_null=True)
    inseam         = serializers.DecimalField(max_digits=6, decimal_places=2, required=False, allow_null=True)
    thigh          = serializers.DecimalField(max_digits=6, decimal_places=2, required=False, allow_null=True)
    knee           = serializers.DecimalField(max_digits=6, decimal_places=2, required=False, allow_null=True)
    ankle          = serializers.DecimalField(max_digits=6, decimal_places=2, required=False, allow_null=True)
    arm_length     = serializers.DecimalField(max_digits=6, decimal_places=2, required=False, allow_null=True)
    bicep          = serializers.DecimalField(max_digits=6, decimal_places=2, required=False, allow_null=True)
    wrist          = serializers.DecimalField(max_digits=6, decimal_places=2, required=False, allow_null=True)
    height         = serializers.DecimalField(max_digits=6, decimal_places=2, required=False, allow_null=True)
    weight_kg      = serializers.DecimalField(max_digits=6, decimal_places=2, required=False, allow_null=True)

    def to_model_data(self, validated_data: dict) -> dict:
        """
        Extract fields suitable for MeasurementProfile model creation/update.
        Excludes service-control fields like set_as_default.
        """
        excluded = {"set_as_default"}
        return {k: v for k, v in validated_data.items() if k not in excluded}
