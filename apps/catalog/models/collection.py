from cloudinary.models import CloudinaryField
from django.conf import settings
from django.db import models
from django.utils import timezone

# pyrefly: ignore [missing-import]
from django.utils.text import slugify

from apps.common.models import SoftDeleteModel, TimeStampedModel


class Collections(TimeStampedModel, SoftDeleteModel):
    """Admin-managed merchandising collection for curated catalog discovery."""

    # ── Core identity ─────────────────────────────────────────────────────
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="catalog_collections",
        db_index=True,
        help_text="Staff user who last created or curated this collection.",
    )
    title = models.CharField(max_length=255, blank=True, null=True)
    sub_title = models.CharField(max_length=255, null=True, blank=True)
    description = models.TextField(null=True, blank=True)
    slug = models.SlugField(unique=True, blank=True, null=True, db_index=True)

    # ── Cloudinary-powered images ─────────────────────────────────────────
    image = CloudinaryField(
        "image",
        folder="fashionistar/catalog/collections/",
        blank=True,
        null=True,
        help_text="Main collection thumbnail image (public_id).",
    )
    background_image = CloudinaryField(
        "background_image",
        folder="fashionistar/catalog/collections/backgrounds/",
        blank=True,
        null=True,
        help_text="Hero background image (public_id).",
    )

    # ── Scheduling & featuring ────────────────────────────────────────────
    is_featured = models.BooleanField(
        default=False,
        db_index=True,
        help_text="Featured collections appear in the homepage featured rail.",
    )
    sort_order = models.PositiveIntegerField(
        default=0,
        db_index=True,
        help_text="Lower value = displayed first.",
    )
    start_date = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
        help_text="Schedule collection go-live datetime (UTC). Null = always live.",
    )
    end_date = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
        help_text="Schedule collection expiry datetime (UTC). Null = never expires.",
    )

    # ── CTA (Call-to-Action) for banners ──────────────────────────────────
    banner_cta_text = models.CharField(
        max_length=100,
        blank=True,
        default="Shop Now",
        help_text="CTA button label shown on collection banner.",
    )
    banner_cta_url = models.CharField(
        max_length=500,
        blank=True,
        help_text="CTA button destination URL (relative or absolute).",
    )

    # ── SEO ───────────────────────────────────────────────────────────────
    meta_title = models.CharField(max_length=180, blank=True)
    meta_description = models.CharField(max_length=320, blank=True)

    # ── Cached counter ────────────────────────────────────────────────────
    cached_product_count = models.PositiveIntegerField(
        default=0,
        help_text="Cached product count. Refreshed by update_collection_product_count Celery task.",
    )
    catalog_tags = models.ManyToManyField(
        "catalog.Tag",
        blank=True,
        related_name="collections",
        help_text="Shared merchandising tags for discovery, campaigns, and future faceted search.",
    )

    class Meta:
        managed = True
        verbose_name = "Catalog Collection"
        verbose_name_plural = "Catalog Collections"
        ordering = ["sort_order", "-created_at"]
        indexes = [
            models.Index(fields=["is_featured", "sort_order"], name="collection_featured_sort_idx"),
            models.Index(fields=["start_date", "end_date"], name="collection_schedule_idx"),
            models.Index(fields=["slug"], name="collection_slug_idx"),
        ]

    def __str__(self):
        return self.title or ""

    @property
    def is_active_now(self) -> bool:
        """Returns True if this collection is within its scheduled window (or has no schedule)."""
        now = timezone.now()
        if self.start_date and now < self.start_date:
            return False
        if self.end_date and now > self.end_date:
            return False
        return True

    def collection_vendor_count(self):
        try:
            return self.vendor_collections.count()
        except Exception:
            return 0

    def collection_vendors(self):
        try:
            return self.vendor_collections.all()
        except Exception:
            return []

    @property
    def product_count(self) -> int:
        """
        Compatibility accessor for read layers expecting product_count.

        In the live repo, collections currently map most directly to vendor
        discovery rather than direct product ownership. This accessor keeps the
        existing cached counter readable without forcing downstream breakage.
        """
        return self.cached_product_count

    def save(self, *args, **kwargs):
        if not self.slug and self.title:
            # pyrefly: ignore [missing-import]
            import shortuuid

            uniqueid = shortuuid.uuid()[:4].lower()
            self.slug = f"{slugify(self.title)}-{uniqueid}"
        super().save(*args, **kwargs)
