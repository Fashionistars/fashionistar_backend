# apps/catalog/models/trending.py
"""
TrendingProduct + FashionTrend — materialized trend signals.

Architecture Rules:
  - TrendingProduct: materialized view refreshed by Celery beat every 6h.
    OneToOneField to Product removed in favour of FK + Period to allow
    separate rows per time window (24h / 7d / 30d).
  - FashionTrend: editor-curated or ML-derived signal, not product-specific.
  - embedding_vector (JSONField) reserved for PgVector migration in 2026.
  - Trend score formula (TrendingProduct):
      trend_score = views*0.4 + orders*0.4 + wishlist*0.2
  - Mutations live in apps/catalog/services/; no business logic here.
"""

from __future__ import annotations

from cloudinary.models import CloudinaryField
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.common.models import TimeStampedModel


class TrendingProduct(TimeStampedModel):
    """
    Materialized trending product entry for a given time window.

    Refreshed by the ``catalog.refresh_trending_products`` Celery beat task
    every 6 hours.  Avoids expensive runtime aggregations at read time.

    Attributes:
        product: Related product entry.
        trend_score: Composite score (views*0.4 + orders*0.4 + wishlist*0.2).
        rank: Ordinal rank within the period (1 = top trending).
        period: Time window: 24h / 7d / 30d.
        refreshed_at: Auto-set on each materialized refresh.
    """

    class Period(models.TextChoices):
        DAY = "24h", _("Last 24 Hours")
        WEEK = "7d", _("Last 7 Days")
        MONTH = "30d", _("Last 30 Days")

    product = models.ForeignKey(
        "product.Product",
        on_delete=models.CASCADE,
        related_name="trending_entries",
        verbose_name=_("Product"),
    )
    trend_score = models.FloatField(
        default=0.0,
        db_index=True,
        verbose_name=_("Trend Score"),
        help_text=_("Composite: views×0.4 + orders×0.4 + wishlist×0.2."),
    )
    rank = models.PositiveIntegerField(
        db_index=True,
        verbose_name=_("Rank"),
        help_text=_("1 = top trending for this period."),
    )
    period = models.CharField(
        max_length=3,
        choices=Period.choices,
        db_index=True,
        verbose_name=_("Period"),
    )
    refreshed_at = models.DateTimeField(
        auto_now=True,
        verbose_name=_("Refreshed At"),
    )

    class Meta:
        verbose_name = _("Trending Product")
        verbose_name_plural = _("Trending Products")
        unique_together = [("product", "period")]
        ordering = ["period", "rank"]
        indexes = [
            models.Index(fields=["period", "rank"], name="tp_period_rank_idx"),
            models.Index(fields=["period", "trend_score"], name="tp_period_score_idx"),
        ]

    def __str__(self) -> str:
        return f"[{self.period}] #{self.rank} {self.product}"


class FashionTrend(TimeStampedModel):
    """
    Platform-level trend entity.

    Editor-curated or ML-derived trend signals for the discovery surface.
    Not product-specific — represents a named cultural/fashion trend.

    Attributes:
        name: Display name (e.g. "Mob Wife Aesthetic").
        slug: URL-safe unique identifier.
        description: Editorial description.
        cover_image: Cloudinary hero image.
        trend_type: Category of trend origin (seasonal, viral, etc.).
        trend_score: ML-computed or editor-assigned score (higher = hotter).
        is_active: Controls storefront visibility.
        featured_until: Auto-expire prominence.
        associated_tags: Taxonomy tags linked to this trend.
        associated_categories: Catalog categories relevant to this trend.
        origin_country / origin_city: Geographic origin metadata.
        embedding_vector: Reserved for semantic similarity search.
    """

    class TrendType(models.TextChoices):
        SEASONAL = "seasonal", _("Seasonal")
        VIRAL = "viral", _("Viral")
        CELEBRITY = "celebrity", _("Celebrity")
        RUNWAY = "runway", _("Runway")
        STREET = "street", _("Street Style")

    name = models.CharField(max_length=150, db_index=True, verbose_name=_("Name"))
    slug = models.SlugField(unique=True, blank=True, verbose_name=_("Slug"))
    description = models.TextField(blank=True, verbose_name=_("Description"))
    cover_image = CloudinaryField(
        "cover_image",
        folder="fashionistar/catalog/trends/",
        blank=True,
        null=True,
        help_text=_("Hero image for this trend."),
    )
    trend_type = models.CharField(
        max_length=10,
        choices=TrendType.choices,
        db_index=True,
        verbose_name=_("Trend Type"),
    )
    trend_score = models.FloatField(
        default=0.0,
        db_index=True,
        verbose_name=_("Trend Score"),
        help_text=_("Higher = hotter. Updated by ML pipeline or editor."),
    )
    is_active = models.BooleanField(
        default=True,
        db_index=True,
        verbose_name=_("Active"),
    )
    featured_until = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("Featured Until"),
    )

    # Taxonomy linkage
    associated_tags = models.ManyToManyField(
        "catalog.Tag",
        blank=True,
        related_name="fashion_trends",
        verbose_name=_("Associated Tags"),
    )
    associated_categories = models.ManyToManyField(
        "catalog.Category",
        blank=True,
        related_name="fashion_trends",
        verbose_name=_("Associated Categories"),
    )

    origin_country = models.CharField(max_length=100, blank=True, verbose_name=_("Origin Country"))
    origin_city = models.CharField(max_length=100, blank=True, verbose_name=_("Origin City"))

    # AI: embedding reserved for PgVector migration
    embedding_vector = models.JSONField(
        null=True,
        blank=True,
        verbose_name=_("Embedding Vector"),
        help_text=_("Float array — reserved for semantic similarity search."),
    )

    class Meta:
        verbose_name = _("Fashion Trend")
        verbose_name_plural = _("Fashion Trends")
        ordering = ["-trend_score", "-created_at"]
        indexes = [
            models.Index(fields=["is_active", "trend_score"], name="ft_active_score_idx"),
            models.Index(fields=["trend_type", "trend_score"], name="ft_type_score_idx"),
        ]

    def __str__(self) -> str:
        return self.name
