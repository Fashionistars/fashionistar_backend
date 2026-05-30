"""
apps/catalog/models/tag.py

Tag — Shared taxonomy label usable across products, blog posts, and collections.
Tags support filtering, trending display, and future faceted search.
"""
from django.db import models
from django.utils.text import slugify

from apps.common.models import SoftDeleteModel, TimeStampedModel


class Tag(TimeStampedModel, SoftDeleteModel):
    """
    Shared taxonomy tag across catalog entities (products, blog, collections).

    Usage:
        product.tags.add(tag)
        BlogPost.tags (JSONField) will migrate to this M2M in Phase B
        CatalogBanner can reference trending tags
    """

    name = models.CharField(
        max_length=60,
        unique=True,
        db_index=True,
        help_text="Unique, human-readable tag label (e.g. 'New Arrivals', 'Sustainable').",
    )
    slug = models.SlugField(
        unique=True,
        db_index=True,
        help_text="Auto-generated URL-safe slug.",
    )
    color_hex = models.CharField(
        max_length=7,
        blank=True,
        help_text="#RRGGBB color for tag badge display.",
    )
    is_trending = models.BooleanField(
        default=False,
        db_index=True,
        help_text="Trending tags surface in the homepage tags rail.",
    )

    class Meta:
        managed = True
        verbose_name = "Catalog Tag"
        verbose_name_plural = "Catalog Tags"
        ordering = ["name"]
        indexes = [
            models.Index(fields=["is_trending", "name"], name="tag_trending_name_idx"),
        ]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug and self.name:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)
