# apps/product/models/product.py
"""
Core product models for the Fashionistar platform.

Migrated from legacy store/models.py and upgraded to the
enterprise-grade modular architecture with:
  - UUID7 primary keys via TimeStampedModel
  - Soft-delete via SoftDeleteModel
  - CloudinaryField for all media
  - Correct on_delete policies (PROTECT on taxonomy, SET_NULL on user refs)
  - Full-text search vector field
  - 2026+ variant / inventory / commission / analytics models
  - Phase 1 expansion: SizeType, Fabric, MeasurementGuide, Certification,
    ShippingProfile, PriceHistory, ViewLog
"""

from decimal import Decimal
import logging
import uuid6
import datetime
from django.utils.timezone import now

from django.contrib.auth import get_user_model
from django.contrib.postgres.indexes import GinIndex
from django.contrib.postgres.search import SearchVectorField
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _

from apps.common.models import TimeStampedModel, SoftDeleteModel, HardDeleteMixin
from apps.order.models import CashPaymentMode

try:
    from cloudinary.models import CloudinaryField
except ImportError:  # pragma: no cover
    from django.db.models import ImageField as CloudinaryField  # type: ignore[assignment]

User = get_user_model()
logger = logging.getLogger(__name__)


import shortuuid
import uuid

STATUS = (
    ("draft", "Draft"),
    ("disabled", "Disabled"),
    ("rejected", "Rejected"),
    ("in_review", "In Review"),
    ("published", "Published"),
)


PAYMENT_STATUS = (
    ("paid", "Paid"),
    ("pending", "Pending"),
    ("processing", "Processing"),
    ("cancelled", "Cancelled"),
    ("initiated", "Initiated"),
    ("failed", "failed"),
    ("refunding", "refunding"),
    ("refunded", "refunded"),
    ("unpaid", "unpaid"),
    ("expired", "expired"),
)


ORDER_STATUS = (
    ("Pending", "Pending"),
    ("Fulfilled", "Fulfilled"),
    ("Partially Fulfilled", "Partially Fulfilled"),
    ("Cancelled", "Cancelled"),
)


OFFER_STATUS = (
    ("accepted", "Accepted"),
    ("rejected", "Rejected"),
    ("pending", "Pending"),
)


PRODUCT_CONDITION_RATING = (
    (1, "1/10"),
    (2, "2/10"),
    (3, "3/10"),
    (4, "4/10"),
    (5, "5/10"),
    (6, "6/10"),
    (7, "7/10"),
    (8, "8/10"),
    (9, "9/10"),
    (10, "10/10"),
)


DELIVERY_STATUS = (
    ("On Hold", "On Hold"),
    ("Shipping Processing", "Shipping Processing"),
    ("Shipped", "Shipped"),
    ("Arrived", "Arrived"),
    ("Returning", "Returning"),
    ("Returned", "Returned"),
    ("Awaiting Pickup", "Awaiting Pickup"),
    ("In Transit", "In Transit"),
    ("Delivered", "Delivered"),
)


RATING = (
    (1, "★☆☆☆☆"),
    (2, "★★☆☆☆"),
    (3, "★★★☆☆"),
    (4, "★★★★☆"),
    (5, "★★★★★"),
)


# ─────────────────────────────────────────────────────────────────────────────
# 1. PRODUCT STATUS CHOICES
# ─────────────────────────────────────────────────────────────────────────────


class ProductStatus(models.TextChoices):
    DRAFT = "draft", _("Draft")
    PENDING = "pending", _("Pending Review")
    PUBLISHED = "published", _("Published")
    ARCHIVED = "archived", _("Archived")
    REJECTED = "rejected", _("Rejected")


# ─────────────────────────────────────────────────────────────────────────────
# 2. TAG
# ─────────────────────────────────────────────────────────────────────────────




class ProductFaq(TimeStampedModel):
    product = models.ForeignKey(
        "Product",
        on_delete=models.CASCADE,
        related_name="product_faqs",
    )
    question = models.CharField(max_length=300)
    answer = models.TextField()

    class Meta:
        verbose_name = _("Product FAQ")
        verbose_name_plural = _("Product FAQs")

    def __str__(self):
        return self.question


# ─────────────────────────────────────────────────────────────────────────────
# 4. PRODUCT (Core)
# ─────────────────────────────────────────────────────────────────────────────


class Product(TimeStampedModel, SoftDeleteModel):
    """
    Canonical product model for Fashionistar.

    Relationships
    -------------
    vendor      → apps.vendor.VendorProfile                                             (PROTECT)
    categories  → apps.catalog.Category                                                 (M2M — one to five product facets)
    tags        → ProductTag                                                            (M2M)

    on_delete rationale
    --------------------
    PROTECT on vendor: a vendor with live products cannot be deleted — must
    soft-delete products first. This prevents orphaned storefront listings.
    Product categories are a capped M2M relationship because one fashion item can
    sit in multiple discovery facets without creating duplicate product rows.
    """

    # ── Identity ──────────────────────────────────────────────────────────
    title = models.CharField(max_length=255, db_index=True)
    slug = models.SlugField(max_length=500, unique=True, blank=True, db_index=True)
    sku = models.CharField(
        max_length=50,
        unique=True,
        blank=True,
        help_text="Auto-generated SKU. Unique across platform.",
    )
    description = models.TextField()

    # ── Taxonomy ──────────────────────────────────────────────────────────
    vendor = models.ForeignKey(
        "vendor.VendorProfile",
        on_delete=models.PROTECT,
        related_name="vendor_products",
        null=True,
        help_text="Vendor who owns this product. PROTECT prevents orphan listings.",
    )
    categories = models.ManyToManyField(
        "catalog.Category",
        related_name="category_products",
        help_text="Canonical product categories. Service layer enforces 1-5 selections.",
    )
    sub_categories = models.ManyToManyField(
        "catalog.Category",
        blank=True,
        related_name="sub_category_products",
        help_text="Optional deeper taxonomy facets. Kept separate from required categories.",
    )
    
    # ── Pricing ───────────────────────────────────────────────────────────
    price = models.DecimalField(max_digits=12, decimal_places=2)
    old_price = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True
    )
    is_discounted = models.BooleanField(default=False)
    discount_percentage = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True
    )
    discounted_price = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True
    )
    currency = models.CharField(max_length=3, default="NGN")
    shipping_amount = models.DecimalField(max_digits=12, decimal_places=2, default=2500)

    # ── Inventory ─────────────────────────────────────────────────────────
    stock_qty = models.PositiveIntegerField(default=0)
    max_stock = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Optional stock ceiling. Service enforces this to prevent over-stocking.",
    )
    in_stock = models.BooleanField(default=True)

    requires_measurement = models.BooleanField(
        default=False,
        help_text="If True, client must share measurement profile before checkout.",
    )
    is_customisable = models.BooleanField(
        default=False,
        help_text="Custom orders — triggers ChatOffer flow.",
    )

    # ── Payment COD / Pay At Shop availability on this product ───────────────────────────────────────────────────────────
    cash_payment_mode = models.CharField(
        max_length=20,
        choices=CashPaymentMode.choices,
        default=CashPaymentMode.DISABLED,
        help_text="Checkout gate for COD / Pay At Shop availability on this product.",
    )
    is_pre_order = models.BooleanField(
        default=False,
        help_text="If True, the product is available for pre-order before stock arrives.",
    )
    pre_order_date = models.DateField(
        null=True,
        blank=True,
        help_text="Expected dispatch date for pre-order items.",
    )

    # ── Status ────────────────────────────────────────────────────────────
    status = models.CharField(
        max_length=20,
        choices=ProductStatus.choices,
        default=ProductStatus.DRAFT,
        db_index=True,
    )
    featured = models.BooleanField(default=False, db_index=True)
    hot_deal = models.BooleanField(default=False)

    # ── Metrics ───────────────────────────────────────────────────────────
    views = models.PositiveIntegerField(default=0)
    orders_count = models.PositiveIntegerField(default=0)
    rating = models.DecimalField(max_digits=3, decimal_places=1, default=0)
    review_count = models.PositiveIntegerField(default=0)

    # ── Platform commission ───────────────────────────────────────────────
    commission_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=10.00,
        help_text="Platform commission % at time of listing. Snapshot on OrderItem.",
    )

    # ── Idempotency (network-retry safe writes) ───────────────────────────
    idempotency_key = models.UUIDField(
        null=True,
        blank=True,
        unique=True,
        db_index=True,
        help_text="Client-generated UUID for safe network-retry. One product per key.",
    )

    condition = models.CharField(
        max_length=20,
        choices=[
            ("new", _("Brand New")),
            ("used", _("Used / Pre-owned")),
            ("refurbished", _("Refurbished")),
        ],
        default="new",
        help_text="Physical condition of the product.",
    )

    # ── SEO Overrides (Phase 1 — 2026) ────────────────────────────────────
    meta_title = models.CharField(
        max_length=160,
        blank=True,
        help_text="SEO title tag override. Defaults to product title when blank.",
    )
    meta_description = models.CharField(
        max_length=320,
        blank=True,
        help_text="SEO meta description override. Shown in search-engine snippets.",
    )

    # ── Demographic targeting (Phase 1 — 2026) ────────────────────────────
    gender_target = models.CharField(
        max_length=20,
        blank=True,
        choices=[
            ("men", _("Men")),
            ("women", _("Women")),
            ("unisex", _("Unisex")),
            ("boys", _("Boys")),
            ("girls", _("Girls")),
            ("kids", _("Kids")),
        ],
        help_text="Primary gender target for catalog segmentation.",
    )
    age_group = models.CharField(
        max_length=20,
        blank=True,
        choices=[
            ("adult", _("Adult")),
            ("teen", _("Teen (13-17)")),
            ("child", _("Child (4-12)")),
            ("toddler", _("Toddler (1-3)")),
            ("infant", _("Infant (0-12 months)")),
        ],
        help_text="Age group this product is designed for.",
    )

    # ── Full-text search ──────────────────────────────────────────────────
    search_vector = SearchVectorField(null=True, blank=True)

    # ── 2026+ AI & Sustainability Fields ─────────────────────────────────
    ai_description = models.TextField(
        blank=True,
        help_text="AI-generated product description. Auto-populated by catalog AI pipeline.",
    )
    style_tags = models.JSONField(
        default=list,
        blank=True,
        help_text="AI-inferred style labels e.g. ['casual','boho','formal']. Used for recommendation engine.",
    )
    occasion_tags = models.JSONField(
        default=list,
        blank=True,
        help_text="AI-inferred occasion labels e.g. ['wedding','everyday','office'].",
    )
    body_type_fit = models.JSONField(
        default=list,
        blank=True,
        help_text="Body types this product is recommended for e.g. ['slim','curvy','athletic'].",
    )
    sustainability_score = models.DecimalField(
        max_digits=4,
        decimal_places=1,
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="Sustainability score 0–100. Computed from material, supply chain, and packaging data.",
    )
    carbon_footprint_kg = models.DecimalField(
        max_digits=8,
        decimal_places=3,
        null=True,
        blank=True,
        help_text="Estimated carbon footprint in kg CO₂ equivalent. Surfaced on product detail page.",
    )
    ai_trend_score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0.00,
        help_text="Trending score 0–100 from AI pipeline. Used to rank catalog feeds.",
    )

    class Meta:
        verbose_name = _("Product")
        verbose_name_plural = _("Products")
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["status", "featured"], name="idx_product_status_featured"
            ),
            models.Index(fields=["vendor"], name="idx_product_vendor"),
            models.Index(fields=["slug"], name="idx_product_slug"),
            GinIndex(fields=["search_vector"], name="idx_product_search_vector"),
        ]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.title)
            slug = base
            counter = 1
            while Product.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base}-{counter}"
                counter += 1
            self.slug = slug
        if not self.sku:
            import uuid as _uuid

            # Use random uuid4 suffix to avoid UNIQUE collisions on rapid creation
            for _attempt in range(5):
                candidate = f"FASTAR-{_uuid.uuid4().hex[:8].upper()}"
                if not Product.objects.filter(sku=candidate).exists():
                    self.sku = candidate
                    break
            else:
                self.sku = f"FASTAR-{_uuid.uuid4().hex[:12].upper()}"
        self.in_stock = self.stock_qty > 0
        super().save(*args, **kwargs)

    @property
    def discount_percentage(self):
        if self.old_price and self.old_price > self.price:
            return round((1 - self.price / self.old_price) * 100)
        return 0

    @property
    def product_review(self):
        """Explicit reverse-manager alias for Product -> ProductReview."""
        return self.reviews

    @property
    def product_wishlist(self):
        """Explicit reverse-manager alias for Product -> ProductWishlist."""
        return self.product_wishlist_entries

    @property
    def primary_category(self):
        """Return the first prefetched category without serializer-side queries."""
        categories = list(self.categories.all()[:1])
        return categories[0] if categories else None

    @property
    def primary_sub_category(self):
        """Return the first prefetched sub-category when one exists."""
        categories = list(self.sub_categories.all()[:1])
        return categories[0] if categories else None

    def category_count(self) -> int:
        """Count published products sharing at least one category with this product."""
        return (
            Product.objects.filter(
                categories__in=self.categories.all(),
                status=ProductStatus.PUBLISHED,
                is_deleted=False,
            )
            .distinct()
            .count()
        )

    async def acategory_count(self) -> int:
        """Async count of published products sharing at least one category."""
        return await (
            Product.objects.filter(
                categories__in=self.categories.all(),
                status=ProductStatus.PUBLISHED,
                is_deleted=False,
            )
            .distinct()
            .acount()
        )

    def get_percentage(self) -> int:
        """Return rounded discount percentage from old_price to price."""
        return int(self.discount_percentage)

    def product_rating(self) -> float:
        """Average active review rating through product.reviews reverse FK."""
        row = self.reviews.filter(active=True).aggregate(avg_rating=models.Avg("rating"))
        return float(row["avg_rating"] or 0)

    async def aproduct_rating(self) -> float:
        """Async average active review rating through product.reviews reverse FK."""
        row = await self.reviews.filter(active=True).aaggregate(
            avg_rating=models.Avg("rating")
        )
        return float(row["avg_rating"] or 0)

    def rating_count(self) -> int:
        """Count active reviews through product.reviews reverse FK."""
        return self.reviews.filter(active=True).count()

    async def arating_count(self) -> int:
        """Async count active reviews through product.reviews reverse FK."""
        return await self.reviews.filter(active=True).acount()

    def order_count(self) -> int:
        """Count paid/completed order snapshots for this product."""
        return self.cart_order_product_snapshots.filter(
            order__status__in=[
                "payment_confirmed",
                "processing",
                "shipped",
                "out_for_delivery",
                "delivered",
                "completed",
            ]
        ).count()

    async def aorder_count(self) -> int:
        """Async count paid/completed order snapshots for this product."""
        return await self.cart_order_product_snapshots.filter(
            order__status__in=[
                "payment_confirmed",
                "processing",
                "shipped",
                "out_for_delivery",
                "delivered",
                "completed",
            ]
        ).acount()

    def gallery(self):
        """Compatibility accessor for unified product_variants_gallery_media queryset."""
        return self.product_variants_gallery_media.filter(is_deleted=False).exclude(media__isnull=True).exclude(media="").order_by(
            "ordering", "created_at"
        )

    async def agallery(self) -> list["ProductVariantGalleryMedia"]:
        """Async list of non-deleted product_variants_gallery_media."""
        return [media async for media in self.gallery()]


    def color(self):
        """Compatibility accessor for colors from variants."""
        colors_list = []
        seen = set()
        for v in self.product_variants_gallery_media.all():
            if v.color_name and v.color_name not in seen:
                seen.add(v.color_name)
                colors_list.append({
                    "id": v.id,
                    "name": v.color_name,
                    "hex_code": v.color_hex,
                })
        return colors_list

    def frequently_bought_together(self, limit: int = 3):
        """Products most often ordered in the same orders as this product."""
        order_ids = self.cart_order_product_snapshots.values("order_id")
        return (
            Product.objects.filter(cart_order_product_snapshots__order_id__in=order_ids)
            .exclude(pk=self.pk)
            .annotate(count=models.Count("cart_order_product_snapshots"))
            .order_by("-count", "-created_at")[:limit]
        )

    async def afrequently_bought_together(self, limit: int = 3) -> list["Product"]:
        """Async products most often ordered in the same orders as this product."""
        return [product async for product in self.frequently_bought_together(limit)]









# ─────────────────────────────────────────────────────────────────────────────
# 6. PRODUCT VARIANT GALLERY MEDIA  (2026+)
# ─────────────────────────────────────────────────────────────────────────────


class ProductVariantGalleryMedia(TimeStampedModel, SoftDeleteModel):
    """
    Consolidated product variant and gallery media model.
    """

    MEDIA_TYPE_CHOICES = [
        ("image", "Image"),
        ("video", "Video"),
    ]

    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="product_variants_gallery_media",
    )
    sku = models.CharField(
        max_length=80,
        unique=True,
        blank=True,
        help_text="Auto-generated SKU. Unique across all variants.",
    )
    size = models.ForeignKey(
        "ProductSizeAndMeasurementGuide",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="product_size_variants",
    )
    color_name = models.CharField(max_length=100, blank=True)
    color_hex = models.CharField(max_length=7, blank=True, help_text="e.g. #FDA600")
   
    media = CloudinaryField(
        "media",
        folder="fashionistar/products/gallery/",
        blank=True,
        null=True,
    )
    media_type = models.CharField(
        max_length=10, choices=MEDIA_TYPE_CHOICES, default="image"
    )
    alt_text = models.CharField(max_length=200, blank=True)

    ordering = models.PositiveSmallIntegerField(default=0)
    is_primary = models.BooleanField(
        default=False,
        help_text="If True, this media item is used as the product cover image on listings.",
    )
    video_thumbnail = CloudinaryField(
        "video_thumbnail",
        folder="fashionistar/products/video_thumbnails/",
        blank=True,
        null=True,
        help_text="Static poster frame for video gallery items. Auto-extracted by Cloudinary.",
    )
    duration_sec = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        help_text="Duration in seconds for video media items.",
    )

    barcode = models.CharField(
        max_length=100,
        blank=True,
        help_text="EAN-13 / UPC-A / QR barcode for warehouse/logistics integrations.",
    )
   
    class Meta:
        verbose_name = _("Product Variant Gallery Media")
        verbose_name_plural = _("Product Variant Gallery Media")
        unique_together = [("product", "size", "color_name")]

    def __str__(self):
        parts = [self.product.title]
        if self.size:
            parts.append(self.size.size_label)
        if self.color_name:
            parts.append(self.color_name)
        return " / ".join(parts)

    def save(self, *args, **kwargs):
        if not self.sku:
            self.sku = f"FASTAR-{str(self.id or uuid6.uuid7()).upper()[:10]}"
        super().save(*args, **kwargs)

    @property
    def effective_price(self):
        return self.price_override if self.price_override is not None else self.product.price



# ─────────────────────────────────────────────────────────────────────────────
# 7. PRODUCT INVENTORY LOG  (2026+)
# ─────────────────────────────────────────────────────────────────────────────


class ProductInventoryLog(TimeStampedModel):
    """
    Append-only stock movement audit trail.
    One row per adjustment — never updated after creation.
    """

    REASON_CHOICES = [
        ("sale", "Sale"),
        ("restock", "Restock"),
        ("adjustment", "Manual Adjustment"),
        ("return", "Customer Return"),
        ("damage", "Damage / Loss"),
        ("reservation", "Cart Reservation"),
        ("release", "Cart Release (Abandoned)"),
        ("refund", "Refund"),
    ]

    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="inventory_logs",
    )
    variant = models.ForeignKey(
        "ProductVariantGalleryMedia",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="inventory_logs",
    )
    actor = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="inventory_adjustments",
    )
    quantity_delta = models.IntegerField(
        help_text="Positive = stock added. Negative = stock removed.",
    )
    quantity_before = models.PositiveIntegerField()
    quantity_after = models.PositiveIntegerField()
    reason = models.CharField(max_length=20, choices=REASON_CHOICES)
    reference_id = models.CharField(
        max_length=100,
        blank=True,
        help_text="Order ID / return ID / manual ref for traceability.",
    )
    note = models.TextField(blank=True)

    class Meta:
        verbose_name = _("Inventory Log")
        verbose_name_plural = _("Inventory Logs")
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.product.title} {self.quantity_delta:+d} ({self.reason})"


# ─────────────────────────────────────────────────────────────────────────────
# 8. PRODUCT REVIEW
# ─────────────────────────────────────────────────────────────────────────────


class ProductReview(TimeStampedModel, SoftDeleteModel):
    """Client review on a product. User SET_NULL on deletion."""

    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="reviews",
    )
    user = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="product_reviews",
    )
    # Snapshot for permanent display even after user deletion
    reviewer_name = models.CharField(max_length=150, blank=True)
    reviewer_email = models.EmailField(blank=True)

    rating = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)],
    )
    review = models.TextField()
    reply = models.TextField(
        blank=True,
        help_text="Vendor reply to this review.",
    )
    active = models.BooleanField(default=True)
    moderated = models.BooleanField(
        default=False,
        help_text="Set by moderator after review.",
    )
    helpful_votes = models.PositiveIntegerField(default=0)
    # Idempotency key — prevents double-review on network retry
    idempotency_key = models.UUIDField(
        null=True,
        blank=True,
        db_index=True,
        help_text="Client-generated UUID. Prevents duplicate review on retry.",
    )

    class Meta:
        verbose_name = _("Product Review")
        verbose_name_plural = _("Product Reviews")
        ordering = ["-created_at"]
        unique_together = [("product", "user")]

    def __str__(self):
        return f"{self.product.title} — {self.rating}★"

    def save(self, *args, **kwargs):
        # Snapshot reviewer info
        if self.user and not self.reviewer_name:
            self.reviewer_name = (
                getattr(self.user, "full_name", "") or self.user.email
                if self.user.email
                else str(self.user.phone) if self.user.phone else ""
            )
        if self.user and not self.reviewer_email:
            self.reviewer_email = (
                self.user.email
                if self.user.email
                else str(self.user.phone) if self.user.phone else ""
            )
        super().save(*args, **kwargs)


# ─────────────────────────────────────────────────────────────────────────────
# 9. PRODUCT WISHLIST
# ─────────────────────────────────────────────────────────────────────────────


class ProductWishlist(TimeStampedModel):
    """
    Client wishlist entry for authenticated and anonymous shoppers.

    Anonymous rows use the same frontend-generated session_key contract as
    Cart, allowing wishlist hearts to survive browser restarts and later be
    reconciled into a real account after login or checkout.
    """

    user = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="user_product_wishlists",
    )
    session_key = models.CharField(
        max_length=40,
        null=True,
        blank=True,
        db_index=True,
        help_text="Frontend-generated anonymous session key. Null for user wishlist.",
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="product_wishlist_entries",
    )

    class Meta:
        verbose_name = _("Product Wishlist")
        verbose_name_plural = _("Product Wishlists")
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(user__isnull=False) | models.Q(session_key__isnull=False)
                ),
                name="wishlist_must_have_user_or_session",
            ),
            models.CheckConstraint(
                condition=~(
                    models.Q(user__isnull=False) & models.Q(session_key__isnull=False)
                ),
                name="wishlist_user_session_exclusive",
            ),
            models.UniqueConstraint(
                fields=["user", "product"],
                condition=models.Q(user__isnull=False),
                name="uniq_user_product_wishlist",
            ),
            models.UniqueConstraint(
                fields=["session_key", "product"],
                condition=models.Q(user__isnull=True, session_key__isnull=False),
                name="uniq_session_product_wishlist",
            ),
        ]

    def __str__(self):
        actor = self.user or f"anon:{self.session_key}"
        return f"{actor} ♥ {self.product.title}"


# ─────────────────────────────────────────────────────────────────────────────
# 10. PRODUCT COMMISSION SNAPSHOT  (2026+)
# ─────────────────────────────────────────────────────────────────────────────


class ProductCommissionSnapshot(TimeStampedModel):
    """
    Captures the platform commission rate at a specific point in time.
    Linked to Product and referenced from OrderItem for financial accuracy.
    """

    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="product_commission_snapshots",
    )
    commission_rate = models.DecimalField(max_digits=5, decimal_places=2)
    effective_from = models.DateTimeField()
    effective_to = models.DateTimeField(null=True, blank=True)
    set_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="product_commission_snapshots_set_by",
    )
    note = models.TextField(blank=True)

    class Meta:
        verbose_name = _("Commission Snapshot")
        ordering = ["-effective_from"]

    def __str__(self):
        return f"{self.product.title} @ {self.commission_rate}%"


# ─────────────────────────────────────────────────────────────────────────────
# 11. COUPON
# ─────────────────────────────────────────────────────────────────────────────


class Coupon(TimeStampedModel, SoftDeleteModel):
    """Discount coupon created by a vendor or platform admin."""

    DISCOUNT_TYPE = [
        ("percentage", "Percentage"),
        ("fixed", "Fixed Amount"),
    ]

    code = models.CharField(max_length=50, unique=True, db_index=True)
    discount_type = models.CharField(
        max_length=12, choices=DISCOUNT_TYPE, default="percentage"
    )
    discount_value = models.DecimalField(max_digits=10, decimal_places=2)
    minimum_order = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    maximum_discount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Cap for percentage coupons.",
    )
    usage_limit = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Total number of times this coupon can be used. Null = unlimited.",
    )
    usage_count = models.PositiveIntegerField(default=0)
    vendor = models.ForeignKey(
        "vendor.VendorProfile",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="vendor_platform_wide_coupons",
        help_text="Null = platform-wide coupon.",
    )
    product = models.ForeignKey(
        Product,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="product_specific_coupon",
        help_text="Null = applies to all products from this vendor.",
    )
    active = models.BooleanField(default=True)
    valid_from = models.DateTimeField()
    valid_to = models.DateTimeField()

    class Meta:
        verbose_name = _("Coupon")
        verbose_name_plural = _("Coupons")

    def __str__(self):
        return f"{self.code} ({self.discount_type}: {self.discount_value})"

    def is_valid(self):
        from django.utils import timezone

        now = timezone.now()
        expired = now > self.valid_to
        usage_exhausted = (
            self.usage_limit is not None and self.usage_count >= self.usage_limit
        )
        return (
            self.active and not expired and not usage_exhausted and not self.is_deleted
        )


# ─────────────────────────────────────────────────────────────────────────────
# 12. DELIVERY COURIER
# ─────────────────────────────────────────────────────────────────────────────


class DeliveryCourier(TimeStampedModel):
    """Platform-registered delivery carrier."""

    name = models.CharField(max_length=120, unique=True)
    active = models.BooleanField(default=True)
    base_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    estimated_days_min = models.PositiveSmallIntegerField(default=1)
    estimated_days_max = models.PositiveSmallIntegerField(default=7)
    logo = CloudinaryField(
        "logo",
        folder="fashionistar/couriers/",
        blank=True,
        null=True,
    )

    class Meta:
        verbose_name = _("Delivery Courier")
        verbose_name_plural = _("Delivery Couriers")

    def __str__(self):
        return self.name


# ─────────────────────────────────────────────────────────────────────────────
# 13. PRODUCT FABRIC SPECIFICATION  (Phase 1 — 2026)
# ─────────────────────────────────────────────────────────────────────────────


class ProductFabricSpecification(TimeStampedModel):
    """
    Fabric type and composition details for a product.

    Displayed on the PDP in the Specifications section.
    Enables fabric-based catalog filtering and material compliance tagging.
    """

    CARE_CHOICES = [
        ("machine_wash", _("Machine Wash")),
        ("hand_wash", _("Hand Wash")),
        ("dry_clean", _("Dry Clean Only")),
        ("do_not_wash", _("Do Not Wash")),
        ("cold_wash", _("Cold Water Wash")),
        ("tumble_dry", _("Tumble Dry Low")),
        ("air_dry", _("Air Dry")),
    ]

    product = models.OneToOneField(
        Product,
        on_delete=models.CASCADE,
        related_name="product_fabric_specification",
        help_text="Each product has at most one Fabric Specification record.",
    )
    fabric_type = models.CharField(
        max_length=120,
        help_text="Primary fabric type e.g. 'Cotton', 'Silk', 'Polyester Blend'.",
    )
    care_instructions = models.CharField(
        max_length=20,
        choices=CARE_CHOICES,
        default="machine_wash",
    )
    is_organic = models.BooleanField(
        default=False, help_text="Certified organic fabric."
    )
    is_vegan = models.BooleanField(
        default=False, help_text="Free from animal-derived materials."
    )

    country_of_origin = models.CharField(
        max_length=80,
        blank=True,
        help_text="Country where the fabric was woven / manufactured. eg. MADE IN ABA, MADE IN ITALY, MADE IN LAGOS etc ",
    )
    class Meta:
        verbose_name = _("Product Fabric Specification")
        verbose_name_plural = _("Product Fabric Specifications")

    def __str__(self):
        return f"{self.fabric_type} - {self.country_of_origin}"


# ─────────────────────────────────────────────────────────────────────────────
# 14. PRODUCT MEASUREMENT GUIDE  (Phase 1 — 2026)
# ─────────────────────────────────────────────────────────────────────────────


class ProductSizeAndMeasurementGuide(TimeStampedModel):
    """
    Size chart row linking a size label to body measurement ranges.

    One row per size per product (or template). Together they form the size guide table.
    
    Reusable size-guide template defined by a vendor (tailor/brand).
    Allows applying a standardized set of measurements (e.g. Senator fit, Kaftan slim fit)
    to a product without manual row-by-row data entry on every upload.
      e.g. 'Clothing', 'Footwear', 'Measurement-Based', 'Custom'.
    Allows the platform to render the correct size picker UI.
    """

    vendor = models.ForeignKey(
        "vendor.VendorProfile",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="measurement_templates",
        help_text="Vendor who owns this reusable sizing template."
    )
    name = models.CharField(max_length=120, help_text="e.g. 'Men's Slim Senator', 'Standard Kaftan'")
    
   
    DESCRIPTION_CHOICES = [
        ("clothing", _("Clothing")),
        ("footwear", _("Footwear")),
        ("accessory", _("Accessory")),
        ("measurement", _("Measurement-Based")),
        ("custom", _("Custom")),
    ]

    description =  models.CharField(
        max_length=20,
        choices=DESCRIPTION_CHOICES,
        default="custom",
        help_text="Description of this measurement guide.",
    )
    
    is_default = models.BooleanField(
        default=False,
        help_text="This is the default measurement guide for this product.",
    )
    
    save_as_template = models.BooleanField(
        default=True,
        help_text="Save this measurement guide as a reusable template for future use.",
    )
    
    SIZE_CHOICES = [
        ("XS", _("XS")),
        ("S", _("S")),
        ("M", _("M")),
        ("L", _("L")),
        ("XL", _("XL")),
        ("XXL", _("XXL")),
        ("Custom", _("Custom")),
    ]

    size_label = models.CharField(
        max_length=30,
        choices=SIZE_CHOICES,
        default="M",
        help_text="Display label e.g. 'XS', 'S', 'M', 'L', 'XL', 'XXL', 'Custom'.",
    )

    chest_cm = models.CharField(
        max_length=20, blank=True, help_text="Chest range e.g. '90-100'."
    )
    waist_cm = models.CharField(
        max_length=20, blank=True, help_text="Waist range e.g. '70-80'."
    )
    hip_cm = models.CharField(
        max_length=20, blank=True, help_text="Hip range e.g. '90-100'."
    )
    length_cm = models.CharField(
        max_length=20, blank=True, help_text="Garment length e.g. '110'."
    )
    shoulder_cm = models.CharField(max_length=20, blank=True)
    sleeve_cm = models.CharField(max_length=20, blank=True)
    inseam_cm = models.CharField(max_length=20, blank=True)
    foot_length_cm = models.CharField(
        max_length=20,
        blank=True,
        help_text="For footwear: foot length in cm.",
    )
    sort_order = models.PositiveSmallIntegerField(
        default=0,
        help_text="Lower value = displayed first in the size picker.",
    )   
    
    class Meta:
        verbose_name = _("Measurement Guide Row")
        verbose_name_plural = _("Measurement Guide Rows")
        ordering = ["sort_order", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["vendor", "name", "size_label"],
                condition=models.Q(vendor__isnull=False),
                name="unique_vendor_template_size_label",
            ),
        ]

    def __str__(self):
        owner = self.vendor.store_name if self.vendor else "Platform"
        return f"{self.name} [{owner}] — {self.size_label}"

# ─────────────────────────────────────────────────────────────────────────────
# 16. PRODUCT SHIPPING PROFILE  (Phase 1 — 2026)
# ─────────────────────────────────────────────────────────────────────────────


class ProductShippingProfile(TimeStampedModel):
    """
    Per-product (or per-variant) shipping configuration.

    Overrides the platform default shipping rules for special items
    (heavy fabrics, fragile accessories, oversized agbadas etc.)
    """

    product = models.OneToOneField(
        Product,
        on_delete=models.CASCADE,
        related_name="product_custom_shipping_profile",
        help_text="Each product has at most one custom shipping profile.",
    )
    weight_kg = models.DecimalField(
        max_digits=7,
        decimal_places=3,
        default=0,
        help_text="Packed weight in kilograms used for shipping rate calculation.",
    )
    dimensions_cm = models.JSONField(
        null=True,
        blank=True,
        help_text='Packed dimensions in cm. Format: {"length": 30, "width": 20, "height": 10}',
    )
    length_cm = models.DecimalField(max_digits=6, decimal_places=1, default=0)
    width_cm = models.DecimalField(max_digits=6, decimal_places=1, default=0)
    height_cm = models.DecimalField(max_digits=6, decimal_places=1, default=0)
    is_fragile = models.BooleanField(default=False)
    requires_signature = models.BooleanField(default=False)
    restricted_countries = models.JSONField(
        default=list,
        blank=True,
        help_text=(
            "ISO-3166-1 alpha-2 country codes where this product cannot be shipped. "
            'Format: ["NG", "GH", "ZA"]'
        ),
    )
    preferred_couriers = models.ManyToManyField(
        DeliveryCourier,
        blank=True,
        related_name="preferred_for_custom_shipping_products",
        help_text="Couriers the vendor prefers for this product.",
        default="DHL,FedEx",

    )
    free_shipping_threshold = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="If order total exceeds this amount, shipping is free. "
        "Null = use platform default.",
    )
    processing_days = models.PositiveSmallIntegerField(
        default=1,
        help_text="Number of business days to prepare the item for dispatch.",
    )

    @property
    def effective_free_shipping_threshold(self) -> Decimal:
        """
        Returns the free shipping threshold for this product.
        Falls back to the PlatformSettings default if not explicitly configured.
        """
        if self.free_shipping_threshold is not None:
            return self.free_shipping_threshold
        from apps.global_platform_settings.cache import get_platform_settings
        try:
            return get_platform_settings().default_free_shipping_threshold
        except Exception:
            return Decimal("50000.00")

    class Meta:
        verbose_name = _("Product Shipping Profile")
        verbose_name_plural = _("Product Shipping Profiles")

    def __str__(self):
        return f"{self.product.title} — {self.weight_kg}kg"


# ─────────────────────────────────────────────────────────────────────────────
# 17. PRODUCT PRICE HISTORY  (Phase 1 — 2026)
# ─────────────────────────────────────────────────────────────────────────────


class ProductPriceHistory(TimeStampedModel):
    """
    Append-only price change audit trail for analytics and trust-building.

    Every time a vendor updates the product price, a new row is appended.
    Rows are NEVER updated — immutable financial ledger.

    Used for:
        - Price drop alerts on wishlisted products
        - Analytics dashboards (pricing trends)
        - Customer trust indicators ("Price dropped 20% last week")
    """

    CHANGE_REASON_CHOICES = [
        ("initial", _("Initial Listing")),
        ("promotion", _("Promotional Price")),
        ("market_adjustment", _("Market Adjustment")),
        ("cost_increase", _("Cost Increase")),
        ("seasonal", _("Seasonal Discount")),
        ("flash_sale", _("Flash Sale")),
        ("correction", _("Price Correction")),
        ("other", _("Other")),
    ]

    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="product_price_history",
    )
    old_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Price before the change. Null for the initial listing.",
    )
    new_price = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default="NGN")
    change_reason = models.CharField(
        max_length=20,
        choices=CHANGE_REASON_CHOICES,
        default="market_adjustment",
    )
    note = models.TextField(blank=True)
    changed_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="custom_product_price_changes",
    )

    class Meta:
        verbose_name = _("Product Price History")
        verbose_name_plural = _("Product Price Histories")
        ordering = ["-created_at"]

    def __str__(self):
        if self.old_price:
            return f"{self.product.title}: {self.old_price} → {self.new_price} ({self.currency})"
        return f"{self.product.title}: Listed at {self.new_price} ({self.currency})"


# ─────────────────────────────────────────────────────────────────────────────
# 18. PRODUCT VIEW LOG  (Phase 1 — 2026)
# ─────────────────────────────────────────────────────────────────────────────


class ProductViewLog(TimeStampedModel):
    """
    Lightweight analytics event for the AI recommendation engine.

    Written asynchronously (Ninja async endpoint) on every PDP view.
    Stores both authenticated user and anonymous session data to
    power collaborative-filtering recommendations.

    Privacy:
        - Anonymous users tracked by session_key only
        - No IP addresses stored
        - User FK is SET_NULL on account deletion
    """

    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="product_view_logs",
    )
    user = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="user_product_views",
        help_text="Authenticated user who viewed the product. Null for anonymous.",
    )
    session_key = models.CharField(
        max_length=40,
        blank=True,
        db_index=True,
        help_text="Django session key for anonymous tracking.",
    )
    referrer_url = models.CharField(
        max_length=500,
        blank=True,
        help_text="URL of the page that linked to this PDP (for traffic attribution).",
    )
    device_type = models.CharField(
        max_length=20,
        blank=True,
        choices=[
            ("desktop", "Desktop"),
            ("mobile", "Mobile"),
            ("tablet", "Tablet"),
            ("unknown", "Unknown"),
        ],
        default="unknown",
    )
    duration_seconds = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        help_text="How long the user spent on the PDP (sent on page leave).",
    )
    utm_source = models.CharField(max_length=100, blank=True)
    utm_medium = models.CharField(max_length=100, blank=True)
    utm_campaign = models.CharField(max_length=100, blank=True)

    class Meta:
        verbose_name = _("Product View Log")
        verbose_name_plural = _("Product View Logs")
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["product", "created_at"], name="idx_viewlog_product_date"
            ),
            models.Index(fields=["user", "created_at"], name="idx_viewlog_user_date"),
            models.Index(fields=["session_key"], name="idx_viewlog_session"),
        ]

    def __str__(self):
        actor = self.user.email if self.user else f"anon:{self.session_key[:8]}"
        return f"{self.product.title} viewed by {actor}"


# ─────────────────────────────────────────────────────────────────────────────
# 19. PRODUCT DRAFT SESSION  (2026+)
# ─────────────────────────────────────────────────────────────────────────────


class ProductDraftStatus(models.TextChoices):
    ACTIVE = "active", _("Active")
    COMMITTED = "committed", _("Committed")
    DISCARDED = "discarded", _("Discarded")
    EXPIRED = "expired", _("Expired")


class ProductDraftSession(HardDeleteMixin, SoftDeleteModel, TimeStampedModel):
    """
    Vendor product builder draft persistence session.
    Keeps unfinished product data resumable for 30 days.
    """

    vendor = models.ForeignKey(
        "vendor.VendorProfile",
        on_delete=models.CASCADE,
        related_name="draft_sessions",
        help_text="Vendor who owns this draft.",
    )
    draft_key = models.UUIDField(db_index=True, unique=True, default=uuid.uuid4)
    idempotency_key = models.UUIDField(db_index=True, null=True, blank=True)
    payload = models.JSONField(help_text="Partial JSON data of the product builder")
    current_step = models.PositiveSmallIntegerField(default=1)
    status = models.CharField(
        max_length=20,
        choices=ProductDraftStatus.choices,
        default=ProductDraftStatus.ACTIVE,
        db_index=True,
    )
    linked_product = models.ForeignKey(
        "product.Product",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="draft_sessions",
        help_text="Populated once the draft is committed to a final Product",
    )
    expires_at = models.DateTimeField(db_index=True)
    last_synced_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Product Draft Session")
        verbose_name_plural = _("Product Draft Sessions")
        ordering = ["-updated_at"]

    def __str__(self):
        return f"Draft {self.draft_key} ({self.status}) for {self.vendor}"

    def check_ownership(self, user) -> bool:
        """Ownership check for HardDeleteMixin."""
        return getattr(user, "vendor_profile", None) == self.vendor

    def save(self, *args, **kwargs):
        if not self.expires_at:
            self.expires_at = now() + datetime.timedelta(days=30)
        super().save(*args, **kwargs)


