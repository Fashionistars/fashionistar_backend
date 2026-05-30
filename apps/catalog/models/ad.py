"""
apps/catalog/models/ad.py

CatalogAd — Paid advertisement campaign slot for vendor-sponsored placements.
Revenue model: vendors pay to place products in featured / hot-deal / category-top slots.

Phase A: Model + admin CRUD only.
Phase B: Budget tracking, impression/click counting, and billing integration.
"""
from django.db import models

from apps.common.models import SoftDeleteModel, TimeStampedModel


class CatalogAdSlot(models.TextChoices):
    HOMEPAGE_FEATURED = "homepage_featured", "Homepage Featured Products"
    HOMEPAGE_HOT_DEAL = "homepage_hot_deal", "Homepage Hot Deals"
    CATEGORY_TOP = "category_top", "Category Page Top Banner"
    COLLECTION_TOP = "collection_top", "Collection Page Top Banner"
    SEARCH_TOP = "search_top", "Search Results Top"
    BLOG_SIDEBAR = "blog_sidebar", "Blog Sidebar"


class CatalogAd(TimeStampedModel, SoftDeleteModel):
    """
    Paid advertisement campaign slot — Phase B ad-platform revenue model.

    Revenue flow:
        Vendor creates ad campaign → Pays budget (Naira) → Product gets boosted
        placement in the targeted slot → Impressions and clicks tracked.

    Future enhancements (Phase B):
        - CPM / CPC billing logic
        - Budget cap and daily spend limits
        - A/B creative testing
        - Vendor self-serve dashboard
    """

    vendor = models.ForeignKey(
        "vendor.VendorProfile",
        on_delete=models.CASCADE,
        related_name="ad_campaigns",
        help_text="Vendor running this ad campaign.",
    )
    product = models.ForeignKey(
        "product.Product",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="ad_campaigns",
        help_text="Specific product to boost. Null = brand/collection-level ad.",
    )

    # ── Placement ─────────────────────────────────────────────────────────
    slot = models.CharField(
        max_length=40,
        choices=CatalogAdSlot.choices,
        db_index=True,
        help_text="Which catalog slot this ad occupies.",
    )

    # ── State & scheduling ────────────────────────────────────────────────
    is_active = models.BooleanField(
        default=False,
        db_index=True,
        help_text="Must be True AND within start/end window to serve.",
    )
    start_date = models.DateTimeField(db_index=True, help_text="Campaign start datetime (UTC).")
    end_date = models.DateTimeField(db_index=True, help_text="Campaign end datetime (UTC).")

    # ── Budget & analytics ────────────────────────────────────────────────
    budget_naira = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        help_text="Total campaign budget in Nigerian Naira (₦).",
    )
    impressions = models.PositiveBigIntegerField(
        default=0,
        help_text="Total ad impressions served (incremented by Celery task).",
    )
    clicks = models.PositiveBigIntegerField(
        default=0,
        help_text="Total ad clicks (incremented by click-tracking endpoint).",
    )

    class Meta:
        managed = True
        verbose_name = "Catalog Ad Campaign"
        verbose_name_plural = "Catalog Ad Campaigns"
        ordering = ["-start_date"]
        indexes = [
            models.Index(
                fields=["slot", "is_active", "start_date", "end_date"],
                name="catalog_ad_slot_active_idx",
            ),
            models.Index(fields=["vendor", "is_active"], name="catalog_ad_vendor_active_idx"),
        ]

    def __str__(self):
        product_title = self.product.title if self.product else "Brand Ad"
        return f"[{self.slot}] {product_title} — ₦{self.budget_naira}"

    @property
    def ctr(self) -> float:
        """Click-Through Rate: clicks / impressions × 100."""
        if not self.impressions:
            return 0.0
        return round((self.clicks / self.impressions) * 100, 2)
