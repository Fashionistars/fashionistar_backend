# apps/catalog/models/style_guide.py
"""
FashionStyleGuide — Editor-curated or AI-generated style guide entity.

Architecture Rules:
  - Inherits TimeStampedModel + SoftDeleteModel from apps.common.
  - CloudinaryField for cover_image (two-phase upload).
  - M2M to Tag (trend_tags) and Product (featured_products).
  - embedding_vector (JSONField) reserved for future AI similarity search.
  - No business logic here — mutations live in apps/catalog/services/.
"""

from __future__ import annotations

from cloudinary.models import CloudinaryField
from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.common.models import SoftDeleteModel, TimeStampedModel


class FashionStyleGuide(TimeStampedModel, SoftDeleteModel):
    """
    AI-generated or editor-curated style guide.

    Powers 'Complete the Look', seasonal editorials, AI trend reports,
    and vendor lookbook suggestions.

    Attributes:
        title: Display title of the guide.
        slug: URL-safe unique identifier.
        description: Long editorial description.
        cover_image: Cloudinary hero image.
        season: Fashion season (SS, AW, PF, CR/Resort).
        year: Publication year (e.g. 2026).
        editor: Staff user who curated/approved the guide.
        trend_tags: Related taxonomy tags.
        featured_products: Products showcased in this guide.
        is_published: Controls storefront visibility.
        published_at: Scheduled publish timestamp.
        view_count: Engagement counter (incremented by Celery task).
        share_count: Social share counter.
        seo_title: SEO override for <title> tag.
        seo_description: Meta description for SEO.
        ai_generated: True if content was AI-drafted.
        ai_prompt_used: Prompt used to generate the guide (audit trail).
        embedding_vector: JSON float array for similarity-based recommendations.
    """

    class Season(models.TextChoices):
        SS = "ss", _("Spring/Summer")
        AW = "aw", _("Autumn/Winter")
        PF = "pf", _("Pre-Fall")
        CR = "cr", _("Cruise/Resort")

    # ── Core fields ───────────────────────────────────────────────────────────
    title = models.CharField(max_length=200, db_index=True, verbose_name=_("Title"))
    slug = models.SlugField(unique=True, blank=True, verbose_name=_("Slug"))
    description = models.TextField(blank=True, verbose_name=_("Description"))
    cover_image = CloudinaryField(
        "cover_image",
        folder="fashionistar/catalog/style-guides/",
        blank=True,
        null=True,
        help_text=_("Hero image — uploaded via Cloudinary two-phase flow."),
    )

    # ── Season / editorial context ────────────────────────────────────────────
    season = models.CharField(
        max_length=3,
        choices=Season.choices,
        blank=True,
        db_index=True,
        verbose_name=_("Season"),
    )
    year = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        db_index=True,
        verbose_name=_("Year"),
        help_text=_("e.g. 2026 — used for seasonal archive."),
    )

    # ── Relationships ─────────────────────────────────────────────────────────
    editor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="style_guides",
        verbose_name=_("Editor"),
        help_text=_("Staff user who curated or approved this guide."),
    )
    trend_tags = models.ManyToManyField(
        "catalog.Tag",
        blank=True,
        verbose_name=_("Trend Tags"),
        help_text=_("Related taxonomy tags for discovery."),
    )
    featured_products = models.ManyToManyField(
        "product.Product",
        blank=True,
        verbose_name=_("Featured Products"),
        help_text=_("Products showcased in this style guide."),
    )

    # ── Publishing ────────────────────────────────────────────────────────────
    is_published = models.BooleanField(
        default=False,
        db_index=True,
        verbose_name=_("Published"),
    )
    published_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("Published At"),
        help_text=_("Scheduled publish time. Null = unpublished."),
    )

    # ── Engagement ───────────────────────────────────────────────────────────
    view_count = models.PositiveIntegerField(default=0, verbose_name=_("View Count"))
    share_count = models.PositiveIntegerField(default=0, verbose_name=_("Share Count"))

    # ── SEO ──────────────────────────────────────────────────────────────────
    seo_title = models.CharField(
        max_length=180,
        blank=True,
        verbose_name=_("SEO Title"),
        help_text=_("Overrides <title> tag if set."),
    )
    seo_description = models.CharField(
        max_length=320,
        blank=True,
        verbose_name=_("SEO Description"),
    )

    # ── AI metadata ──────────────────────────────────────────────────────────
    ai_generated = models.BooleanField(
        default=False,
        verbose_name=_("AI Generated"),
        help_text=_("True if content was AI-drafted."),
    )
    ai_prompt_used = models.TextField(
        blank=True,
        verbose_name=_("AI Prompt Used"),
        help_text=_("Audit: the prompt used to generate this guide."),
    )
    embedding_vector = models.JSONField(
        null=True,
        blank=True,
        verbose_name=_("Embedding Vector"),
        help_text=_("Float array from embedding model — reserved for similarity search."),
    )

    class Meta:
        verbose_name = _("Fashion Style Guide")
        verbose_name_plural = _("Fashion Style Guides")
        ordering = ["-published_at", "-created_at"]
        indexes = [
            models.Index(fields=["slug"], name="sg_slug_idx"),
            models.Index(fields=["season", "year"], name="sg_season_year_idx"),
            models.Index(fields=["is_published", "published_at"], name="sg_pub_idx"),
        ]

    def __str__(self) -> str:
        return self.title
