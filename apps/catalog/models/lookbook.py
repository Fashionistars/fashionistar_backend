# apps/catalog/models/lookbook.py
"""
Lookbook + LookbookItem — vendor or editorial curated product collection.

Architecture Rules:
  - Lookbook: SoftDeleteModel + TimeStampedModel (editorial asset).
  - LookbookItem: TimeStampedModel only (line item — no soft-delete needed).
  - gallery_images stores ordered list of Cloudinary public_ids (JSONField).
  - position_x / position_y store hotspot coords (0–100%) for product tagging.
  - Mutations live in apps/catalog/services/; no business logic here.
"""

from __future__ import annotations

from cloudinary.models import CloudinaryField
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.common.models import SoftDeleteModel, TimeStampedModel


class Lookbook(TimeStampedModel, SoftDeleteModel):
    """
    Vendor or editorial lookbook.

    A curated selection of products with editorial imagery,
    published to the storefront for discovery and inspiration.

    gallery_images format:
        ["fashionistar/lookbooks/vendor_123/img1", "fashionistar/lookbooks/vendor_123/img2"]

    Attributes:
        vendor: Owning VendorProfile. Null = platform editorial lookbook.
        style_guide: Optional link to a FashionStyleGuide season.
        title: Display name.
        slug: URL-safe unique identifier.
        description: Editorial copy.
        cover_image: Cloudinary hero image.
        gallery_images: Ordered list of Cloudinary public_ids.
        is_published: Storefront visibility flag.
        published_at: Scheduled publish timestamp.
        featured_until: Auto-expire feature prominence.
        likes_count: Social engagement counter.
        views_count: View counter (updated by Celery task).
    """

    vendor = models.ForeignKey(
        "vendor.VendorProfile",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="lookbooks",
        verbose_name=_("Vendor"),
        help_text=_("Vendor owner. Null = platform editorial lookbook."),
    )
    style_guide = models.ForeignKey(
        "catalog.FashionStyleGuide",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="lookbooks",
        verbose_name=_("Style Guide"),
    )
    title = models.CharField(max_length=200, db_index=True, verbose_name=_("Title"))
    slug = models.SlugField(unique=True, blank=True, verbose_name=_("Slug"))
    description = models.TextField(blank=True, verbose_name=_("Description"))
    cover_image = CloudinaryField(
        "cover_image",
        folder="fashionistar/catalog/lookbooks/",
        blank=True,
        null=True,
        help_text=_("Hero image — two-phase Cloudinary upload."),
    )
    # Ordered list of Cloudinary public_ids for the gallery carousel
    gallery_images = models.JSONField(
        default=list,
        blank=True,
        verbose_name=_("Gallery Images"),
        help_text=_("Ordered list of Cloudinary public_ids."),
    )

    is_published = models.BooleanField(default=False, db_index=True, verbose_name=_("Published"))
    published_at = models.DateTimeField(null=True, blank=True, verbose_name=_("Published At"))
    featured_until = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("Featured Until"),
        help_text=_("Auto-expire feature prominence after this datetime."),
    )

    likes_count = models.PositiveIntegerField(default=0, verbose_name=_("Likes"))
    views_count = models.PositiveIntegerField(default=0, verbose_name=_("Views"))

    class Meta:
        verbose_name = _("Lookbook")
        verbose_name_plural = _("Lookbooks")
        ordering = ["-published_at", "-created_at"]
        indexes = [
            models.Index(fields=["vendor", "is_published"], name="lb_vendor_pub_idx"),
            models.Index(fields=["is_published", "featured_until"], name="lb_featured_idx"),
        ]

    def __str__(self) -> str:
        vendor = self.vendor_id and f" ({self.vendor})" or " [Editorial]"
        return f"{self.title}{vendor}"


class LookbookItem(TimeStampedModel):
    """
    Individual product within a Lookbook.

    Supports hotspot tagging (position_x / position_y as % of image width/height)
    to enable interactive 'shop this look' overlays on imagery.

    Attributes:
        lookbook: Parent Lookbook.
        product: Tagged product.
        sort_order: Display order within the lookbook.
        annotation_text: Short caption shown on hover.
        position_x: Horizontal hotspot position (0.0–100.0%).
        position_y: Vertical hotspot position (0.0–100.0%).
    """

    lookbook = models.ForeignKey(
        Lookbook,
        on_delete=models.CASCADE,
        related_name="items",
        verbose_name=_("Lookbook"),
    )
    product = models.ForeignKey(
        "product.Product",
        on_delete=models.CASCADE,
        related_name="lookbook_items",
        verbose_name=_("Product"),
    )
    sort_order = models.PositiveSmallIntegerField(default=0, verbose_name=_("Sort Order"))
    annotation_text = models.CharField(
        max_length=200,
        blank=True,
        verbose_name=_("Annotation"),
        help_text=_("Short caption displayed on hover."),
    )
    # Hotspot coords as percentage of image dimensions (0.0–100.0)
    position_x = models.FloatField(
        null=True,
        blank=True,
        verbose_name=_("Position X (%)"),
        help_text=_("Horizontal hotspot position (0–100%)."),
    )
    position_y = models.FloatField(
        null=True,
        blank=True,
        verbose_name=_("Position Y (%)"),
        help_text=_("Vertical hotspot position (0–100%)."),
    )

    class Meta:
        verbose_name = _("Lookbook Item")
        verbose_name_plural = _("Lookbook Items")
        ordering = ["sort_order"]
        unique_together = [("lookbook", "product")]

    def __str__(self) -> str:
        return f"{self.lookbook} → {self.product}"
