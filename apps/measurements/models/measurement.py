# apps/measurements/models/measurement.py
"""
Measurement domain models for Fashionistar.

Architecture:
  - MeasurementProfile: stores a client's full body measurements.
  - Measurements are stored in centimetres by default; a `unit` field
    allows future display in inches without schema migration.
  - Cloudinary is used for storing reference photos (optional).
  - Products with `requires_measurement=True` BLOCK checkout unless the
    buyer has a validated `MeasurementProfile`.

Measurement fields follow ISO/tailoring industry standards:
  bust, waist, hips, shoulder_width, inseam, thigh, knee, ankle,
  arm_length, neck, height, weight.

Design decisions:
  - One primary profile per user per name (default: "My Measurements").
  - A user may create multiple profiles (e.g., "Slim Fit", "Casual").
  - `is_verified`: admin/vendor can manually validate measurements.
  - `reference_photo`: Cloudinary direct-upload for measurement guide photo.
  - Soft-delete via TimeStampedModel is NOT included here — measurements
    are sensitive data but not regulatory-critical like orders.
    Hard-delete is acceptable on user request (GDPR right-to-erasure).
"""

import logging

from cloudinary.models import CloudinaryField
from django.contrib.auth import get_user_model
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.common.models import TimeStampedModel

User = get_user_model()
logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# ENUM HELPERS
# ─────────────────────────────────────────────────────────────────────────────

class MeasurementUnit(models.TextChoices):
    CM   = "cm",    _("Centimetres")
    INCH = "inch",  _("Inches")


class BodySide(models.TextChoices):
    LEFT  = "left",  _("Left")
    RIGHT = "right", _("Right")
    BOTH  = "both",  _("Both")


# ─────────────────────────────────────────────────────────────────────────────
# MEASUREMENT PROFILE
# ─────────────────────────────────────────────────────────────────────────────

class MeasurementProfile(TimeStampedModel):
    """
    A named set of body measurements for a client.

    Usage gate:
      Before checkout of a `requires_measurement=True` product, the
      service layer validates that the buyer has at least one
      MeasurementProfile. If not, checkout raises
      MeasurementRequiredError (HTTP 422).

    Storage:
      All measurements stored as DecimalField(cm). The `unit` field
      controls display conversion — not storage.

    Cloudinary reference photo:
      - Sub-folder: fashionistar/measurements/<user_id>/
      - Upload preset: CLOUDINARY_UPLOAD_PRESET_MEASURE
      - Two-phase direct-upload (client → Cloudinary → webhook callback)
    """

    owner = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="measurement_profiles",
        help_text="The client who owns this measurement profile.",
    )
    name = models.CharField(
        max_length=100,
        default="My Measurements",
        help_text="Profile label, e.g. 'Slim Fit', 'Maternity', 'Gym Build'.",
    )
    is_default = models.BooleanField(
        default=False,
        help_text="Mark as the user's default profile for checkout gating.",
    )
    unit = models.CharField(
        max_length=4,
        choices=MeasurementUnit.choices,
        default=MeasurementUnit.CM,
    )

    # ── Torso ────────────────────────────────────────────────────────────────
    bust = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(300)],
        help_text="Bust/chest circumference (cm).",
    )
    waist = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(300)],
        help_text="Natural waist circumference (cm).",
    )
    hips = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(300)],
        help_text="Hip circumference at the fullest point (cm).",
    )
    shoulder_width = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="Shoulder seam to seam across the back (cm).",
    )
    neck = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="Neck base circumference (cm).",
    )

    # ── Lower body ───────────────────────────────────────────────────────────
    inseam = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(200)],
        help_text="Inseam length (cm).",
    )
    thigh = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(200)],
        help_text="Thigh circumference at the fullest point (cm).",
    )
    knee = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="Knee circumference (cm).",
    )
    ankle = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="Ankle circumference (cm).",
    )

    # ── Arms ─────────────────────────────────────────────────────────────────
    arm_length = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(200)],
        help_text="Arm length from shoulder to wrist (cm).",
    )
    bicep = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="Bicep circumference at the fullest point (cm).",
    )
    wrist = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(50)],
        help_text="Wrist circumference (cm).",
    )

    # ── Full body ─────────────────────────────────────────────────────────────
    height = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(300)],
        help_text="Total height (cm).",
    )
    weight_kg = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(500)],
        help_text="Weight in kilograms (for fabric allowance).",
    )

    # ── Reference photo (Cloudinary) ─────────────────────────────────────────
    reference_photo = CloudinaryField(
        "reference_photo",
        folder="fashionistar/measurements",
        blank=True,
        null=True,
        help_text=(
            "Full-body reference photo for measurement verification. "
            "Uploaded via Cloudinary direct-upload two-phase flow."
        ),
    )

    # ── Admin verification ────────────────────────────────────────────────────
    is_verified = models.BooleanField(
        default=False,
        help_text=(
            "Set by admin/vendor after manually validating measurements. "
            "Some vendors may require verified profiles for high-end custom orders."
        ),
    )
    verified_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="verified_measurements",
        help_text="Staff user who verified this measurement profile.",
    )
    notes = models.TextField(
        blank=True,
        help_text="Optional notes from client or tailor (e.g. 'prefer relaxed fit').",
    )

    class Meta:
        verbose_name        = _("Measurement Profile")
        verbose_name_plural = _("Measurement Profiles")
        ordering            = ["-is_default", "-updated_at"]
        indexes             = [
            models.Index(
                fields=["owner", "is_default"],
                name="idx_measure_owner_default",
            ),
        ]
        unique_together = [("owner", "name")]

    def __str__(self):
        return f"{self.owner} | {self.name}"

    def to_cm(self, value):
        """Convert a stored cm value to the profile's display unit."""
        if value is None:
            return None
        if self.unit == MeasurementUnit.INCH:
            return round(float(value) / 2.54, 2)
        return float(value)

    @property
    def has_core_measurements(self) -> bool:
        """
        Returns True if the minimum required measurements for custom tailoring
        are present (bust OR chest, waist, hips, height).
        """
        return all(
            v is not None for v in [self.waist, self.hips, self.height]
        ) and (self.bust is not None)

    def set_as_default(self):
        """
        Atomically set this profile as the user's default, clearing any
        existing default. Call within a transaction.atomic() block.
        """
        from django.db import transaction
        with transaction.atomic():
            MeasurementProfile.objects.filter(
                owner=self.owner,
                is_default=True,
            ).exclude(pk=self.pk).update(is_default=False)
            self.is_default = True
            self.save(update_fields=["is_default", "updated_at"])
