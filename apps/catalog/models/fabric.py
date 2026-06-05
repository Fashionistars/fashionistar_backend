# apps/catalog/models/fabric.py
"""
Fabric — textile material entity for product detail and care instructions.

Architecture Rules:
  - Inherits TimeStampedModel from apps.common (no soft-delete needed for reference data).
  - composition, care_instructions, properties all use JSONField for flexibility.
  - sustainability_score: 0–100 to enable sustainability filters and badges.
  - texture_image: CloudinaryField for fabric swatch photography.
  - No business logic here — mutations in apps/catalog/services/.
"""

from __future__ import annotations

from cloudinary.models import CloudinaryField
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.common.models import TimeStampedModel


class Fabric(TimeStampedModel):
    """
    Textile / fabric material entity.

    Used in Product detail pages to provide:
    - Fiber composition breakdowns (e.g. 80% Cotton, 20% Polyester)
    - Care instruction icons / labels
    - Sustainability ratings and eco-badges
    - Fabric properties for discovery filtering (breathable, stretch, waterproof)

    Attributes:
        name: Material name (e.g. "Pure Silk", "Organic Cotton Blend").
        slug: URL-safe unique identifier.
        description: Editorial description of the material.
        composition: Fiber percentage breakdown (JSON).
        care_instructions: List of care codes / labels (JSON).
        texture_image: Cloudinary fabric swatch photo.
        properties: Fabric property flags (JSON boolean map).
        sustainability_score: 0 (poorest) – 100 (best) eco-rating.
        origin_country: Primary source country.
        is_active: Controls admin/storefront availability.

    JSON field formats:
        composition:
            {"cotton": 80, "polyester": 15, "elastane": 5}

        care_instructions:
            ["machine_wash_cold", "do_not_bleach", "tumble_dry_low", "iron_low"]

        properties:
            {
                "breathable": true,
                "stretch": true,
                "waterproof": false,
                "wrinkle_resistant": true,
                "anti_static": false
            }
    """

    name = models.CharField(
        max_length=150,
        unique=True,
        db_index=True,
        verbose_name=_("Name"),
    )
    slug = models.SlugField(unique=True, blank=True, verbose_name=_("Slug"))
    description = models.TextField(blank=True, verbose_name=_("Description"))

    # ── Composition ───────────────────────────────────────────────────────────
    composition = models.JSONField(
        default=dict,
        verbose_name=_("Composition"),
        help_text=_('Fiber percentage breakdown. E.g. {"cotton": 80, "polyester": 20}'),
    )

    # ── Care ─────────────────────────────────────────────────────────────────
    care_instructions = models.JSONField(
        default=list,
        verbose_name=_("Care Instructions"),
        help_text=_(
            'List of care codes. '
            'E.g. ["machine_wash_cold", "do_not_bleach", "tumble_dry_low"]'
        ),
    )

    # ── Media ─────────────────────────────────────────────────────────────────
    texture_image = CloudinaryField(
        "texture_image",
        folder="fashionistar/catalog/fabrics/",
        blank=True,
        null=True,
        help_text=_("Fabric swatch / texture photo — two-phase Cloudinary upload."),
    )

    # ── Properties ───────────────────────────────────────────────────────────
    properties = models.JSONField(
        default=dict,
        verbose_name=_("Properties"),
        help_text=_(
            'Boolean property map. '
            'E.g. {"breathable": true, "stretch": false, "waterproof": false}'
        ),
    )

    # ── Sustainability ────────────────────────────────────────────────────────
    sustainability_score = models.PositiveSmallIntegerField(
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        verbose_name=_("Sustainability Score"),
        help_text=_("0 = poorest, 100 = best eco-rating."),
    )
    origin_country = models.CharField(
        max_length=100,
        blank=True,
        verbose_name=_("Origin Country"),
        help_text=_("Primary textile production country."),
    )

    is_active = models.BooleanField(default=True, db_index=True, verbose_name=_("Active"))

    class Meta:
        verbose_name = _("Fabric")
        verbose_name_plural = _("Fabrics")
        ordering = ["name"]
        indexes = [
            models.Index(fields=["is_active", "sustainability_score"], name="fab_active_eco_idx"),
        ]

    def __str__(self) -> str:
        return self.name

    @property
    def composition_display(self) -> str:
        """Human-readable composition string, e.g. '80% Cotton, 20% Polyester'."""
        if not self.composition:
            return ""
        parts = [f"{pct}% {fiber.title()}" for fiber, pct in self.composition.items()]
        return ", ".join(parts)
