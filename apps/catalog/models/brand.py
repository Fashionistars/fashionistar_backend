# pyrefly: ignore [missing-import]
from cloudinary.models import CloudinaryField

# pyrefly: ignore [missing-import]
from django.conf import settings

# pyrefly: ignore [missing-import]
from django.db import models
from django.utils.html import mark_safe

# pyrefly: ignore [missing-import]
from django.utils.text import slugify

from apps.common.models import SoftDeleteModel, TimeStampedModel


class Brand(SoftDeleteModel, TimeStampedModel):
    """Admin-managed brand metadata used by public catalog discovery."""

    # ── Core identity ─────────────────────────────────────────────────────
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="catalog_brands",
        db_index=True,
        help_text="Staff user who last created or curated this brand.",
    )
    title = models.CharField(max_length=100)
    description = models.TextField(null=True, blank=True)
    slug = models.SlugField(unique=True, blank=True, null=True, db_index=True)
    active = models.BooleanField(default=True, db_index=True)

    # ── Cloudinary images ─────────────────────────────────────────────────
    image = CloudinaryField(
        "image",
        folder="fashionistar/catalog/brands/",
        blank=True,
        null=True,
        help_text=(
            "Cloudinary image public_id. "
            "Set via the /api/v1/upload/presign/ → direct upload → webhook flow. "
            "Use .url in serializers to retrieve the full HTTPS secure_url."
        ),
    )
    logo_banner = CloudinaryField(
        "logo_banner",
        folder="fashionistar/catalog/brands/banners/",
        blank=True,
        null=True,
        help_text="Wide-format logo / hero banner for brand detail page.",
    )

    # ── Extended brand metadata ───────────────────────────────────────────
    country = models.CharField(
        max_length=60,
        blank=True,
        help_text="Country of origin (e.g. 'Nigeria', 'Ghana', 'South Africa').",
    )
    website_url = models.URLField(blank=True)
    established_year = models.PositiveSmallIntegerField(
        null=True, blank=True, help_text="Year the brand was established."
    )

    # ── Trust & placement flags ───────────────────────────────────────────
    verified = models.BooleanField(
        default=False,
        db_index=True,
        help_text="Admin-verified brand. Shows a verified badge.",
    )
    premium = models.BooleanField(
        default=False,
        db_index=True,
        help_text="Premium placement slot — shown first in brand grids.",
    )

    # ── SEO ───────────────────────────────────────────────────────────────
    meta_title = models.CharField(max_length=180, blank=True)
    meta_description = models.CharField(max_length=320, blank=True)

    # ── Cached counter ────────────────────────────────────────────────────
    cached_product_count = models.PositiveIntegerField(
        default=0,
        help_text="Cached product count. Refreshed by update_brand_product_count Celery task.",
    )

    class Meta:
        managed = True
        verbose_name = "Catalog Brand"
        verbose_name_plural = "Catalog Brands"
        ordering = ["-premium", "title"]
        indexes = [
            models.Index(fields=["verified", "premium"], name="brand_verified_premium_idx"),
            models.Index(fields=["slug"], name="brand_slug_idx"),
        ]

    def brand_image(self):
        if not self.image:
            return "No Image"
        return mark_safe(
            f'<img src="{self.image.url}" width="50" height="50" '
            'style="object-fit:cover; border-radius: 6px;" />'
        )

    def __str__(self):
        return self.title or ""

    def save(self, *args, **kwargs):
        if not self.slug and self.title:
            import shortuuid

            uniqueid = shortuuid.uuid()[:4].lower()
            self.slug = f"{slugify(self.title)}-{uniqueid}"
        super().save(*args, **kwargs)
