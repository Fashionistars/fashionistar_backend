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
  - 2026+ variant / inventory / commission models
"""

import logging
import uuid6

from django.contrib.auth import get_user_model
from django.contrib.postgres.indexes import GinIndex
from django.contrib.postgres.search import SearchVectorField
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _

from apps.common.models import TimeStampedModel, SoftDeleteModel

try:
    from cloudinary.models import CloudinaryField
except ImportError:  # pragma: no cover
    from django.db.models import ImageField as CloudinaryField  # type: ignore[assignment]

User = get_user_model()
logger = logging.getLogger(__name__)


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


class ProductTag(TimeStampedModel):
    """Flat taxonomy tag. Can optionally be linked to a catalog category."""

    name = models.CharField(max_length=80, unique=True, db_index=True)
    slug = models.SlugField(max_length=100, unique=True, blank=True)

    # Optional link to catalog for faceted navigation
    category = models.ForeignKey(
        "catalog.Category",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="product_tags",
    )

    class Meta:
        verbose_name = _("Product Tag")
        verbose_name_plural = _("Product Tags")
        ordering = ["name"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)


# ─────────────────────────────────────────────────────────────────────────────
# 3. PRODUCT SIZE / COLOR / SPECIFICATION
# ─────────────────────────────────────────────────────────────────────────────


class ProductSize(models.Model):
    name = models.CharField(max_length=30)  # e.g. XS, S, M, L, XL, XXL, Custom

    class Meta:
        verbose_name = _("Product Size")
        verbose_name_plural = _("Product Sizes")

    def __str__(self):
        return self.name


class ProductColor(models.Model):
    name = models.CharField(max_length=50)
    hex_code = models.CharField(max_length=7, blank=True, help_text="e.g. #FDA600")

    class Meta:
        verbose_name = _("Product Color")
        verbose_name_plural = _("Product Colors")

    def __str__(self):
        return self.name


class ProductSpecification(TimeStampedModel):
    product = models.ForeignKey(
        "Product",
        on_delete=models.CASCADE,
        related_name="specifications",
    )
    title = models.CharField(max_length=120)
    content = models.CharField(max_length=500)

    class Meta:
        verbose_name = _("Product Specification")
        verbose_name_plural = _("Product Specifications")

    def __str__(self):
        return f"{self.product.title} — {self.title}"


class ProductFaq(TimeStampedModel):
    product = models.ForeignKey(
        "Product",
        on_delete=models.CASCADE,
        related_name="faqs",
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
    vendor      → apps.vendor.VendorProfile (PROTECT)
    category    → apps.catalog.Category     (SET_NULL — catalog is metadata)
    brand       → apps.catalog.Brand        (SET_NULL)
    tags        → ProductTag                (M2M)
    sizes       → ProductSize               (M2M)
    colors      → ProductColor              (M2M)

    on_delete rationale
    --------------------
    PROTECT on vendor: a vendor with live products cannot be deleted — must
    soft-delete products first. This prevents orphaned storefront listings.
    SET_NULL on category/brand: catalog taxonomy can be restructured without
    destroying product history.
    """

    # ── Identity ──────────────────────────────────────────────────────────
    title = models.CharField(max_length=255, db_index=True)
    slug = models.SlugField(max_length=300, unique=True, blank=True, db_index=True)
    sku = models.CharField(
        max_length=50,
        unique=True,
        blank=True,
        help_text="Auto-generated SKU. Unique across platform.",
    )
    description = models.TextField()
    short_description = models.CharField(max_length=300, blank=True)

    # ── Taxonomy ──────────────────────────────────────────────────────────
    vendor = models.ForeignKey(
        "vendor.VendorProfile",
        on_delete=models.PROTECT,
        related_name="products",
        null=True,
        help_text="Vendor who owns this product. PROTECT prevents orphan listings.",
    )
    category = models.ForeignKey(
        "catalog.Category",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="products",
    )
    sub_category = models.ForeignKey(
        "catalog.Category",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="sub_products",
    )
    brand = models.ForeignKey(
        "catalog.Brand",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="products",
    )
    tags = models.ManyToManyField(ProductTag, blank=True, related_name="products")
    sizes = models.ManyToManyField(ProductSize, blank=True, related_name="products")
    colors = models.ManyToManyField(ProductColor, blank=True, related_name="products")

    # ── Pricing ───────────────────────────────────────────────────────────
    price = models.DecimalField(max_digits=12, decimal_places=2)
    old_price = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True
    )
    currency = models.CharField(max_length=3, default="NGN")
    shipping_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    # ── Inventory ─────────────────────────────────────────────────────────
    stock_qty = models.PositiveIntegerField(default=0)
    in_stock = models.BooleanField(default=True)
    requires_measurement = models.BooleanField(
        default=False,
        help_text="If True, client must share measurement profile before checkout.",
    )
    is_customisable = models.BooleanField(
        default=False,
        help_text="Custom orders — triggers ChatOffer flow.",
    )

    # ── Media ─────────────────────────────────────────────────────────────
    image = CloudinaryField(
        "image",
        folder="fashionistar/products/",
        blank=True,
        null=True,
        help_text="Primary product image. Set via direct-upload presign flow.",
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
    digital = models.BooleanField(default=False)

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

    # ── Full-text search ──────────────────────────────────────────────────
    search_vector = SearchVectorField(null=True, blank=True)

    class Meta:
        verbose_name = _("Product")
        verbose_name_plural = _("Products")
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["status", "featured"], name="idx_product_status_featured"
            ),
            models.Index(fields=["vendor"], name="idx_product_vendor"),
            models.Index(fields=["category"], name="idx_product_category"),
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
                candidate = f"FSN-{_uuid.uuid4().hex[:8].upper()}"
                if not Product.objects.filter(sku=candidate).exists():
                    self.sku = candidate
                    break
            else:
                self.sku = f"FSN-{_uuid.uuid4().hex[:12].upper()}"
        self.in_stock = self.stock_qty > 0
        super().save(*args, **kwargs)

    @property
    def discount_percentage(self):
        if self.old_price and self.old_price > self.price:
            return round((1 - self.price / self.old_price) * 100)
        return 0


# ─────────────────────────────────────────────────────────────────────────────
# 5. PRODUCT GALLERY MEDIA
# ─────────────────────────────────────────────────────────────────────────────


class ProductGalleryMedia(TimeStampedModel, SoftDeleteModel):
    """Multiple media attachments for a product. Replaces legacy Gallery model."""

    MEDIA_TYPE_CHOICES = [
        ("image", "Image"),
        ("video", "Video"),
    ]

    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="gallery",
    )
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

    class Meta:
        verbose_name = _("Product Gallery Media")
        verbose_name_plural = _("Product Gallery Media")
        ordering = ["ordering", "created_at"]

    def __str__(self):
        return f"{self.product.title} — {self.media_type} #{self.ordering}"


# ─────────────────────────────────────────────────────────────────────────────
# 6. PRODUCT VARIANT  (2026+)
# ─────────────────────────────────────────────────────────────────────────────


class ProductVariant(TimeStampedModel):
    """
    Per-variant SKU with optional price override and separate stock count.

    Supports size+color combinations for fashion items.
    """

    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="variants",
    )
    sku = models.CharField(max_length=80, unique=True, blank=True)
    size = models.ForeignKey(
        ProductSize,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="variants",
    )
    color = models.ForeignKey(
        ProductColor,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="variants",
    )
    price_override = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="If set, overrides the parent product price for this variant.",
    )
    stock_qty = models.PositiveIntegerField(default=0)
    image = CloudinaryField(
        "variant_image",
        folder="fashionistar/products/variants/",
        blank=True,
        null=True,
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = _("Product Variant")
        verbose_name_plural = _("Product Variants")
        unique_together = [("product", "size", "color")]

    def __str__(self):
        parts = [self.product.title]
        if self.size:
            parts.append(self.size.name)
        if self.color:
            parts.append(self.color.name)
        return " / ".join(parts)

    def save(self, *args, **kwargs):
        if not self.sku:
            self.sku = f"VAR-{str(self.id or uuid6.uuid7()).upper()[:10]}"
        super().save(*args, **kwargs)

    @property
    def effective_price(self):
        return self.price_override if self.price_override else self.product.price


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
    ]

    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="inventory_logs",
    )
    variant = models.ForeignKey(
        ProductVariant,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
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


class ProductReview(TimeStampedModel):
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
    """Client wishlist entry. Deleted when user is deleted (CASCADE)."""

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="wishlist",
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="wishlist_entries",
    )

    class Meta:
        verbose_name = _("Product Wishlist")
        verbose_name_plural = _("Product Wishlists")
        unique_together = [("user", "product")]

    def __str__(self):
        return f"{self.user} ♥ {self.product.title}"


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
        related_name="commission_snapshots",
    )
    commission_rate = models.DecimalField(max_digits=5, decimal_places=2)
    effective_from = models.DateTimeField()
    effective_to = models.DateTimeField(null=True, blank=True)
    set_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="commission_adjustments",
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
        related_name="coupons",
        help_text="Null = platform-wide coupon.",
    )
    product = models.ForeignKey(
        Product,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="coupons",
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
