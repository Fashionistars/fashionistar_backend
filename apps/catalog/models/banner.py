"""
apps/catalog/models/banner.py

CatalogBanner — CMS-managed homepage hero / mid-page / footer CTA slots.
Banners are Cloudinary-hosted, scheduled (start/end date), and admin-controlled.
They are served via the asyncio.gather() homepage bundle endpoint and cached in Redis.
"""
from cloudinary.models import CloudinaryField
from django.db import models

from apps.common.models import SoftDeleteModel, TimeStampedModel


class BannerSlot(models.TextChoices):
    HERO = "hero", "Hero Carousel"
    MID = "mid", "Mid-Page Banner"
    FOOTER_CTA = "footer_cta", "Footer CTA"


class CatalogBanner(TimeStampedModel, SoftDeleteModel):
    """
    Homepage hero banner slot — CMS-managed, scheduled, Cloudinary-hosted.

    Slot types:
        hero       → Full-width hero carousel (top of homepage)
        mid        → Mid-page campaign banner (between sections)
        footer_cta → Bottom-of-page conversion banner

    Scheduling:
        start_date=None → always live from creation
        end_date=None   → never expires automatically
    """

    slot = models.CharField(
        max_length=20,
        choices=BannerSlot.choices,
        db_index=True,
        help_text="Which homepage slot this banner occupies.",
    )
    title = models.CharField(max_length=200)
    subtitle = models.CharField(max_length=400, blank=True)
    cta_text = models.CharField(
        max_length=80,
        blank=True,
        default="Shop Now",
        help_text="Call-to-action button label.",
    )
    cta_url = models.CharField(
        max_length=500,
        blank=True,
        help_text="CTA destination URL (relative or absolute).",
    )

    # ── Cloudinary images ─────────────────────────────────────────────────
    image = CloudinaryField(
        "image",
        folder="fashionistar/catalog/banners/",
        blank=True,
        null=True,
        help_text="Desktop banner image (recommended: 1920×600).",
    )
    mobile_image = CloudinaryField(
        "mobile_image",
        folder="fashionistar/catalog/banners/mobile/",
        blank=True,
        null=True,
        help_text="Mobile banner image (recommended: 390×500).",
    )

    # ── Display ───────────────────────────────────────────────────────────
    sort_order = models.PositiveIntegerField(
        default=0,
        help_text="Lower = displayed first within the carousel.",
    )
    is_active = models.BooleanField(default=True, db_index=True)

    # ── Scheduling ────────────────────────────────────────────────────────
    start_date = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
        help_text="Go-live datetime (UTC). Null = immediately active.",
    )
    end_date = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
        help_text="Expiry datetime (UTC). Null = never expires.",
    )

    class Meta:
        managed = True
        verbose_name = "Catalog Banner"
        verbose_name_plural = "Catalog Banners"
        ordering = ["sort_order", "-created_at"]
        indexes = [
            models.Index(fields=["slot", "is_active"], name="banner_slot_active_idx"),
            models.Index(fields=["slot", "start_date", "end_date"], name="banner_slot_schedule_idx"),
        ]

    def __str__(self):
        return f"[{self.slot}] {self.title}"

    @property
    def image_url(self) -> str:
        return self.image.url if self.image else ""

    @property
    def mobile_image_url(self) -> str:
        return self.mobile_image.url if self.mobile_image else ""
