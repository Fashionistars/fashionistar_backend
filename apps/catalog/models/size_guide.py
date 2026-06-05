# apps/catalog/models/size_guide.py
"""
SizeChart + SizeRecommendation — AI-driven size matching entities.

Architecture Rules:
  - SizeChart: reusable reference data, scoped to Category and/or Brand.
  - SizeRecommendation: AI output linking a MeasurementProfile to a size.
  - chart_data uses JSONField for flexible multi-region size tables.
  - Confidence score (0.0–1.0) required for all AI recommendations.
  - Mutations live in apps/catalog/services/ (size_guide_service.py).

chart_data format:
  {
    "XS": {"bust": [80, 84], "waist": [60, 64], "hips": [86, 90]},
    "S":  {"bust": [84, 88], "waist": [64, 68], "hips": [90, 94]},
    "M":  {"bust": [88, 92], "waist": [68, 72], "hips": [94, 98]}
  }
"""

from __future__ import annotations

from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.common.models import TimeStampedModel


class SizeChart(TimeStampedModel):
    """
    Reusable size chart for a Category or Brand.

    Maps industry size labels (XS, S, M, etc.) to measurement ranges
    stored in centimetres (default) or inches.

    Attributes:
        name: Display name (e.g. "Women's EU Sizing — Dresses").
        slug: URL-safe unique identifier.
        category: Optional link to a catalog Category.
        brand: Optional link to a catalog Brand.
        gender: Target gender for this size chart.
        size_type: Type of garment/item (clothing, shoes, accessories).
        chart_data: JSON size → measurement range mapping.
        unit: Measurement unit stored in chart_data.
        is_active: Controls API/storefront availability.
        sort_order: Display priority (lower = first).
    """

    class Gender(models.TextChoices):
        MALE = "male", _("Male")
        FEMALE = "female", _("Female")
        UNISEX = "unisex", _("Unisex")
        CHILDREN = "children", _("Children")

    class SizeType(models.TextChoices):
        CLOTHING = "clothing", _("Clothing")
        SHOES = "shoes", _("Shoes")
        ACCESSORIES = "accessories", _("Accessories")

    class Unit(models.TextChoices):
        CM = "cm", _("Centimetres")
        INCH = "inch", _("Inches")

    name = models.CharField(max_length=150, db_index=True, verbose_name=_("Name"))
    slug = models.SlugField(unique=True, blank=True, verbose_name=_("Slug"))
    category = models.ForeignKey(
        "catalog.Category",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="size_charts",
        verbose_name=_("Category"),
    )
    brand = models.ForeignKey(
        "catalog.Brand",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="size_charts",
        verbose_name=_("Brand"),
    )
    gender = models.CharField(
        max_length=10,
        choices=Gender.choices,
        db_index=True,
        verbose_name=_("Gender"),
    )
    size_type = models.CharField(
        max_length=12,
        choices=SizeType.choices,
        db_index=True,
        verbose_name=_("Size Type"),
    )
    chart_data = models.JSONField(
        verbose_name=_("Chart Data"),
        help_text=_(
            'Size-to-measurement range mapping. '
            'E.g. {"XS": {"bust": [80,84], "waist": [60,64]}}'
        ),
    )
    unit = models.CharField(
        max_length=4,
        choices=Unit.choices,
        default=Unit.CM,
        verbose_name=_("Unit"),
    )
    is_active = models.BooleanField(default=True, db_index=True, verbose_name=_("Active"))
    sort_order = models.PositiveSmallIntegerField(default=0, verbose_name=_("Sort Order"))

    class Meta:
        verbose_name = _("Size Chart")
        verbose_name_plural = _("Size Charts")
        ordering = ["sort_order", "name"]
        indexes = [
            models.Index(fields=["gender", "size_type"], name="sc_gender_type_idx"),
            models.Index(fields=["category", "is_active"], name="sc_cat_active_idx"),
        ]

    def __str__(self) -> str:
        return self.name

    def get_size_for_measurement(self, field: str, value_cm: float) -> str | None:
        """
        Return the recommended size label for a single measurement value.

        Args:
            field: Measurement field name (e.g. "bust", "waist").
            value_cm: Client's measurement in centimetres.

        Returns:
            Size label (e.g. "M") or None if no range matches.
        """
        for size_label, ranges in self.chart_data.items():
            field_range = ranges.get(field)
            if field_range and len(field_range) == 2:
                lo, hi = field_range
                if lo <= value_cm <= hi:
                    return size_label
        return None


class SizeRecommendation(TimeStampedModel):
    """
    AI-generated size recommendation.

    Links a client's MeasurementProfile to a recommended size on a SizeChart.
    Created by the AI size recommendation service after a scan or manual entry.

    Attributes:
        measurement_profile: The client's measurement data used for recommendation.
        size_chart: The size chart evaluated.
        recommended_size: Primary recommended size label (e.g. "M").
        confidence_score: Model confidence (0.0 = low, 1.0 = high).
        reasoning: Human-readable explanation of the recommendation.
        generated_at: Auto-set on creation.
        model_version: ML model version string for reproducibility audits.
    """

    measurement_profile = models.ForeignKey(
        "measurements.MeasurementProfile",
        on_delete=models.CASCADE,
        related_name="size_recommendations",
        verbose_name=_("Measurement Profile"),
    )
    size_chart = models.ForeignKey(
        SizeChart,
        on_delete=models.CASCADE,
        related_name="recommendations",
        verbose_name=_("Size Chart"),
    )
    recommended_size = models.CharField(
        max_length=10,
        verbose_name=_("Recommended Size"),
    )
    confidence_score = models.FloatField(
        verbose_name=_("Confidence Score"),
        help_text=_("0.0 = low confidence, 1.0 = high confidence."),
    )
    reasoning = models.TextField(
        blank=True,
        verbose_name=_("Reasoning"),
        help_text=_("AI explanation of why this size was recommended."),
    )
    generated_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_("Generated At"),
    )
    model_version = models.CharField(
        max_length=50,
        blank=True,
        verbose_name=_("Model Version"),
        help_text=_("ML model version for reproducibility audit."),
    )

    class Meta:
        verbose_name = _("Size Recommendation")
        verbose_name_plural = _("Size Recommendations")
        unique_together = [("measurement_profile", "size_chart")]
        ordering = ["-generated_at"]

    def __str__(self) -> str:
        return (
            f"{self.measurement_profile} → {self.size_chart.name}: "
            f"{self.recommended_size} ({self.confidence_score:.0%})"
        )
