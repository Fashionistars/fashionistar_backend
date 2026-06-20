from cloudinary.models import CloudinaryField
from django.conf import settings
from django.db import models
from django.utils.html import mark_safe
from django.utils.text import slugify

from apps.common.models import SoftDeleteModel, TimeStampedModel


class Category(TimeStampedModel, SoftDeleteModel):
    """Admin-managed public product category metadata owned by catalog."""

    # ── Hierarchy ─────────────────────────────────────────────────────────
    parent = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_index=True,
        related_name="children",
        help_text="Parent category for hierarchical browsing. Null = root category.",
    )

    # ── Core identity ─────────────────────────────────────────────────────
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="catalog_categories",
        db_index=True,
        help_text="Staff user who last created or curated this category.",
    )
    name = models.CharField(max_length=100, unique=True, db_index=True)
    slug = models.SlugField(unique=True, blank=True, null=True, db_index=True)

    # ── Cloudinary images ─────────────────────────────────────────────────
    image = CloudinaryField(
        "image",
        folder="fashionistar/catalog/categories/",
        blank=True,
        null=True,
        help_text=(
            "Cloudinary image public_id. "
            "Set via the /api/v1/upload/presign/ → direct upload → webhook flow. "
            "Use .url in serializers to retrieve the full HTTPS secure_url."
        ),
    )
    banner_image = CloudinaryField(
        "banner_image",
        folder="fashionistar/catalog/categories/banners/",
        blank=True,
        null=True,
        help_text="Hero banner shown on the category detail / listing page.",
    )

    # ── SEO ───────────────────────────────────────────────────────────────
    meta_title = models.CharField(max_length=180, blank=True)
    meta_description = models.CharField(max_length=320, blank=True)

    # ── Sort / Order ────────────────────────────────────────────────────────
    sort_order = models.PositiveIntegerField(
        default=0,
        db_index=True,
        help_text="Lower value = displayed first in grids.",
    )
    icon_class = models.CharField(
        max_length=60,
        blank=True,
        help_text="CSS icon class or SVG slug (e.g. 'icon-dress', 'lucide-shirt').",
    )
    
    # ── Cached Counter (updated async by Celery task) ─────────────────────
    cached_product_count = models.PositiveIntegerField(
        default=0,
        db_index=True,
        help_text="Cached product count. Refreshed by update_category_product_count Celery task.",
    )

    # ── Phase 12: 2026+ Scale Fields ─────────────────────────────────────────
    # Hierarchy materialization (avoids recursive queries for depth/path)
    depth = models.PositiveSmallIntegerField(
        default=0,
        help_text="Hierarchy depth. 0 = root category. Updated on save.",
    )
    full_path = models.CharField(
        max_length=500, blank=True, db_index=True,
        help_text="Materialized full slug path: 'fashion/women/dresses'. Updated on save.",
    )
    is_leaf_node = models.BooleanField(
        default=True, db_index=True,
        help_text="True if this category has no children. Updated by Celery beat.",
    )

    # AI & Discovery
    ai_trend_score = models.FloatField(
        default=0.0, db_index=True,
        help_text="AI-computed trend score (0.0 – 100.0). Refreshed every 6 hours.",
    )
    season_relevance = models.JSONField(
        default=dict, blank=True,
        help_text='Season-to-relevance score: {"SS": 0.9, "AW": 0.3}.',
    )
    gender_tags = models.JSONField(
        default=list, blank=True,
        help_text='Target gender list: ["female", "male", "unisex", "children"].',
    )
    embedding_vector = models.JSONField(
        null=True, blank=True,
        help_text="768-dim embedding for category similarity matching.",
    )

    class Meta:
        managed = True
        verbose_name = "Catalog Category"
        verbose_name_plural = "Catalog Categories"
        ordering = ["sort_order", "name"]
        indexes = [
            models.Index(fields=["name"], name="category_name_idx"),
            models.Index(fields=["slug"], name="category_slug_idx"),
            models.Index(fields=["parent", "sort_order"], name="category_parent_sort_idx"),
            models.Index(fields=["is_deleted", "sort_order"], name="category_is_deleted_sort_idx"),
            models.Index(fields=["is_leaf_node", "is_deleted"], name="category_leaf_is_deleted_idx"),
            models.Index(fields=["ai_trend_score"], name="category_trend_score_idx"),
        ]


    # ── Admin helpers ─────────────────────────────────────────────────────
    def category_image(self):
        if not self.image:
            return "No Image"
        return mark_safe(
            f'<img src="{self.image.url}" width="50" height="50" '
            'style="object-fit:cover; border-radius: 6px;" />'
        )

    def __str__(self):
        return self.name or ""

    # ── Product count ─────────────────────────────────────────────────────
    def product_count(self):
        """Return cached counter. Use get_live_product_count() for real-time accuracy."""
        return self.cached_product_count

    def get_live_product_count(self):
        """Live DB count — slower; use only in admin or Celery tasks."""
        try:
            return self.category_products.count()
        except Exception:
            return 0

    def cat_products(self):
        try:
            return self.category_products.all()
        except Exception:
            return []

    # ── Save hook ─────────────────────────────────────────────────────────
    def save(self, *args, **kwargs):
        # pyrefly: ignore [missing-import]
        import shortuuid

        if not self.slug and self.name:
            uniqueid = shortuuid.uuid()[:4].lower()
            self.slug = f"{slugify(self.name)}-{uniqueid}"
        super().save(*args, **kwargs)
