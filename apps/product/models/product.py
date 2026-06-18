# apps/product/models/product.py
"""Core product database models for the Fashionistar platform.

Aligned and optimized to support the high-fashion digital marketplace. Includes
UUID7-based primary keys, soft-deletion boundaries, and consolidated structures
for variants, sizing guides, and logistics.

Model Architecture Map:
  - Section 1: Auxiliary Taxonomy Models (ProductTag, DeliveryCourier)
  - Section 2: Core Product Model (Product, ProductFaq)
  - Section 3: Sizing & Fabric Configurations (ProductSizeAndMeasurementGuide, ProductFabricSpecification)
  - Section 4: Unified Variants & Media (ProductVariantGalleryMedia)
  - Section 5: Logistics & Shipping Profiles (ProductShippingProfile)
  - Section 6: Financials & Policy Tracking (ProductCommissionSnapshot, Coupon, ProductPriceHistory)
  - Section 7: Ledgers & Customer Review Trackers (ProductInventoryLog, ProductReview, ProductViewLog)
  - Section 8: Persistence & Wishlist Trackers (ProductDraftSession, ProductWishlist)
"""

from typing import Optional
from typing import Any
from decimal import Decimal
import logging
import uuid
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

try:
    from cloudinary.models import CloudinaryField
except ImportError:  # pragma: no cover
    from django.db.models import ImageField as CloudinaryField  # type: ignore[assignment]

User = get_user_model()
logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 1: AUXILIARY TAXONOMY MODELS
# ─────────────────────────────────────────────────────────────────────────────

class ProductTag(TimeStampedModel):
    """Flat classification tags utilized for catalog search filtering.

    Linked optionally to a Category to allow targeted faceted navigation.
    """

    name = models.CharField(max_length=80, unique=True, db_index=True)
    slug = models.SlugField(max_length=100, unique=True, blank=True)
    category = models.ForeignKey(
        "catalog.Category",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="category_product_tags",
    )

    class Meta:
        verbose_name = _("Product Tag")
        verbose_name_plural = _("Product Tags")
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Enforces safe slug generation based on user name input."""
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)


class DeliveryCourier(TimeStampedModel):
    """Platform-registered logistics courier profiles.

    Powers shipping profile delivery calculations and courier selections.
    """

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

    def __str__(self) -> str:
        return self.name


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 2: CORE PRODUCT MODELS
# ─────────────────────────────────────────────────────────────────────────────

class ProductStatus(models.TextChoices):
    """Workflow state validation choices for listed products."""
    DRAFT = "draft", _("Draft")
    PENDING = "pending", _("Pending Review")
    PUBLISHED = "published", _("Published")
    ARCHIVED = "archived", _("Archived")
    REJECTED = "rejected", _("Rejected")


class Product(TimeStampedModel, SoftDeleteModel):
    """Canonical model storing core properties of a listed design piece.

    Maintains relationships to categories, pricing fields, metric histories,
    demographics, SEO metadata, and sustainability/AI properties.
    """

    # Identity properties
    title = models.CharField(max_length=255, db_index=True)
    slug = models.SlugField(max_length=500, unique=True, blank=True, db_index=True)
    """
    Unique SKU identifier generated automatically upon saving.
    is BEEN SHIFTED AND ADDED STRAIGHT TO THE PRODUCTVARIANTGALLERYMEDIA MODEL
    SO THAT EACH PRODUCT VARIANTS CAN HAVE THEIR OWN UNIQUE SKU
    ENDING WITH THEIR UNIQUE COLOR AND SIZE.
    """
    description = models.TextField()

    # Ownership & Classification relationships
    vendor = models.ForeignKey(
        "vendor.VendorProfile",
        on_delete=models.PROTECT,
        related_name="vendor_products",
        null=True,
        help_text="The associated designer storefront profile.",
    )
    categories = models.ManyToManyField(
        "catalog.Category",
        related_name="category_products",
        help_text="Primary classification groups. Capped at 1 to 15 allocations.",
    )
    sub_categories = models.ManyToManyField(
        "catalog.Category",
        blank=True,
        related_name="sub_category_products",
        help_text="Deep classification groups used for recommendation indices.",
    )
    tags = models.ManyToManyField(ProductTag, blank=True, related_name="tag_products")

    # Financial and pricing attributes
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

    # Inventory & Policy definitions
    stock_qty = models.PositiveIntegerField(default=0)
    max_stock = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Operational threshold to prevent oversell situations.",
    )
    in_stock = models.BooleanField(default=True)
    requires_measurement = models.BooleanField(
        default=False,
        help_text="Forces the buyer to submit exact body sizes prior to checking out.",
    )
    is_customisable = models.BooleanField(
        default=False,
        help_text="Allows customization requests via direct negotiation.",
    )
    
    # Payment & Fulfillment configurations
    class CashPaymentMode(models.TextChoices):
        DISABLED = "disabled", _("Disabled")
        COD = "cod", _("Cash On Delivery")
        PAY_AT_SHOP = "pay_at_shop", _("Pay At Shop")
        PAYMENT_ON_DELIVERY = "payment_on_delivery", _("Payment On Delivery")
        PAYMENT_BEFORE_DELIVERY = "payment_before_delivery", _("Payment Before Delivery")
        PART_PAYMENT_BEFORE_DELIVERY = "part_payment_before_delivery", _("Part Payment Before Delivery")
        ALLOW_ALL = "allow_all", _("Allow All")
    
    cash_payment_mode = models.CharField(
        max_length=32,  # longest value: 'part_payment_before_delivery' (28 chars)
        choices=CashPaymentMode.choices,
        default=CashPaymentMode.DISABLED,
        help_text="Enables or disables Cash on Delivery (COD) channels.",
    )
    is_pre_order = models.BooleanField(
        default=False,
        help_text="Specifies if items can be purchased prior to materials arriving.",
    )
    pre_order_date = models.DateField(
        null=True,
        blank=True,
        help_text="Estimated shipment date for pre-order purchases.",
    )
    
    # Workflow properties
    status = models.CharField(
        max_length=20,
        choices=ProductStatus.choices,
        default=ProductStatus.DRAFT,
        db_index=True,
    )
    featured = models.BooleanField(default=False, db_index=True)
    hot_deal = models.BooleanField(default=False)

    # Metrics & Engagement variables
    views = models.PositiveIntegerField(default=0)
    orders_count = models.PositiveIntegerField(default=0)
    rating = models.DecimalField(max_digits=3, decimal_places=1, default=0)
    review_count = models.PositiveIntegerField(default=0)
    commission_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=10.00,
        help_text="Calculated platform cut snapshot recorded on item listings.",
    )

    # Idempotency token to prevent write collisions
    idempotency_key = models.UUIDField(
        null=True,
        blank=True,
        unique=True,
        db_index=True,
        help_text="Unique key generated on client forms to prevent network duplications.",
    )
    condition = models.CharField(
        max_length=20,
        choices=[
            ("new", _("Brand New")),
            ("used", _("Used / Pre-owned")),
            ("refurbished", _("Refurbished")),
        ],
        default="new",
    )
    # Shipping profile (OneToOne: each product has at most one shipping profile)
    shipping_profile = models.OneToOneField(
        "product.ProductShippingProfile",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="product_shipping_profiles",
    )

    # Search and SEO overrides
    meta_title = models.CharField(
        max_length=160,
        blank=True,
        help_text="SEO title tag override. Defaults to product title when blank.",
    )
    meta_description = models.CharField(
        max_length=320,
        blank=True,
        help_text="SEO description tag override, Optional search snippet descriptive block.",
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
        help_text="Age-segment target for catalog organization.",
    )
    # FAQs are accessed via the reverse manager: product.faqs.all()
    # (ForeignKey is defined on ProductFaq.product below)


    # ── Full-text search ──────────────────────────────────────────────────
    search_vector = SearchVectorField(null=True, blank=True)

    # System ML and Analytical features (Private fields)
    ai_description = models.TextField(blank=True)
    style_tags = models.JSONField(default=list, blank=True)
    occasion_tags = models.JSONField(default=list, blank=True)
    body_type_fit = models.JSONField(default=list, blank=True)
    sustainability_score = models.DecimalField(
        max_digits=4,
        decimal_places=1,
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="Sustainability score 0–100. Computed from material, supply chain, and packaging data.",
    )
    carbon_footprint_kg = models.DecimalField(
        max_digits=8, decimal_places=3, null=True, blank=True,
        help_text="Estimated CO₂e in kilograms per unit, computed from materials, dyeing, and transport legs.",
    )
    ai_trend_score = models.DecimalField(
        max_digits=5, decimal_places=2, default=0.00,
        help_text="Trendiness index (0–100). Computed from trending hashtags, sales velocity, and social buzz.",
    )

    # ── Style and curation ──────────────────────────────────────────────────

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

    def __str__(self) -> str:
        return self.title

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Enforces unique slug assignment and random SKU checks upon saving."""
        if not self.slug:
            base = slugify(self.title)
            slug = base
            counter = 1
            while Product.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base}-{counter}"
                counter += 1
            self.slug = slug
        self.in_stock = self.stock_qty > 0
        super().save(*args, **kwargs)

    @property
    def discount_percentage_calc(self) -> int:
        """Calculates current catalog markdown percentages from old_price."""
        if self.old_price and self.old_price > self.price:
            return round((1 - self.price / self.old_price) * 100)
        return 0

    @property
    def product_review(self):
        """Explicit reverse-manager alias for Product -> ProductReview."""
        return self.reviews

    @property
    def product_wishlist(self) -> models.QuerySet:
        """Explicit reverse accessor property redirecting to wishlist entries."""
        return self.product_wishlist_entries

    @property
    def primary_category(self) -> Optional[models.Model]:
        """Resolves the primary categorization level with zero N+1 overhead."""
        categories = list(self.categories.all()[:1])
        return categories[0] if categories else None

    @property
    def primary_sub_category(self) -> Optional[models.Model]:
        """Resolves the first sub-categorization level with zero N+1 overhead."""
        categories = list(self.sub_categories.all()[:1])
        return categories[0] if categories else None

    @property
    def image(self):
        """Returns the primary media object or the first media object in the gallery."""
        variants = self.product_gallery_media.all()
        if isinstance(variants, list):
            primary = next((v.media for v in variants if getattr(v, "is_primary", False) and not getattr(v, "is_deleted", False) and v.media), None)
            if primary:
                return primary
            first = next((v.media for v in variants if not getattr(v, "is_deleted", False) and v.media), None)
            return first
        try:
            primary = variants.filter(is_primary=True, is_deleted=False).first()
            if primary and primary.media:
                return primary.media
            first = variants.filter(is_deleted=False).exclude(media__isnull=True).exclude(media="").first()
            if first and first.media:
                return first.media
        except Exception:
            pass
        return None

    def gallery(self) -> models.QuerySet:
        """Collects non-deleted variant media assets with valid paths."""
        return self.product_variants_gallery_media.filter(is_deleted=False).exclude(media__isnull=True).exclude(media="").order_by(
            "ordering", "created_at"
        )

    @property
    def sku(self) -> str:
        """Returns the SKU of the first variant if available, else a generated fallback or empty string."""
        prefetched = getattr(self, "_prefetched_variants", None)
        if prefetched:
            return prefetched[0].sku
        
        prefetch_cache = getattr(self, "_prefetched_objects_cache", {}) or {}
        if "product_variants_gallery_media" in prefetch_cache:
            v_list = prefetch_cache["product_variants_gallery_media"]
            if v_list:
                return v_list[0].sku
        
        from django.core.exceptions import SynchronousOnlyOperation
        try:
            first_variant = self.product_variants_gallery_media.filter(is_deleted=False).first()
            if first_variant:
                return first_variant.sku
        except SynchronousOnlyOperation:
            # Fallback for async contexts where variants are not prefetched
            return ""
        return ""

    @property
    def product_gallery_media(self):
        """Related manager alias that respects prefetch caches."""
        class PrefetchedManagerAlias:
            def __init__(self, parent):
                self.parent = parent

            def all(self):
                prefetched = getattr(self.parent, "_prefetched_variants", None)
                if prefetched is not None:
                    return prefetched
                prefetch_cache = getattr(self.parent, "_prefetched_objects_cache", {}) or {}
                if "product_variants_gallery_media" in prefetch_cache:
                    return prefetch_cache["product_variants_gallery_media"]
                if "product_gallery_media" in prefetch_cache:
                    return prefetch_cache["product_gallery_media"]
                return self.parent.product_variants_gallery_media.all()
        return PrefetchedManagerAlias(self)

    @property
    def product_measurement_guide(self):
        """Returns the measurement guides associated with this product's variants or vendor."""
        class GuideManagerAlias:
            def __init__(self, parent):
                self.parent = parent

            def all(self):
                prefetched = getattr(self.parent, "_prefetched_measurement_guides", None)
                if prefetched is not None:
                    return prefetched
                prefetch_cache = getattr(self.parent, "_prefetched_objects_cache", {}) or {}
                if "product_measurement_guide" in prefetch_cache:
                    return prefetch_cache["product_measurement_guide"]
                size_ids = self.parent.product_variants_gallery_media.filter(
                    is_deleted=False
                ).exclude(size__isnull=True).values_list("size_id", flat=True).distinct()
                if size_ids:
                    return ProductSizeAndMeasurementGuide.objects.filter(id__in=size_ids).order_by("sort_order")
                if self.parent.vendor:
                    return ProductSizeAndMeasurementGuide.objects.filter(
                        vendor=self.parent.vendor
                    ).order_by("sort_order")
                return ProductSizeAndMeasurementGuide.objects.none()
        return GuideManagerAlias(self)

    @property
    def product_fabric(self):
        """Related object alias for product_fabric_specification."""
        try:
            return self.product_fabric_specification
        except Exception:
            return None

    @property
    def product_custom_shipping_profile(self):
        """Related object alias for shipping_profile."""
        try:
            return self.shipping_profile
        except Exception:
            return None

    @property
    def measurement_template(self) -> Optional[str]:
        """Backward compatibility for deleted measurement_template field."""
        guide = self.product_measurement_guide.all()
        if isinstance(guide, list) and guide:
            return guide[0].name
        elif hasattr(guide, "first"):
            first = guide.first()
            if first:
                return first.name
        return None

    @property
    def weight_kg(self) -> Decimal:
        """Backward compatibility for deleted weight_kg field."""
        profile = self.shipping_profile
        return getattr(profile, "weight_kg", Decimal("0.0"))

    def color(self) -> list[dict[str, Any]]:
        """Extracts unique color values across associated product variants."""
        colors_list = []
        seen = set()
        for v in self.product_variants_gallery_media.all():
            if v.color_name and v.color_name not in seen:
                seen.add(v.color_name)
                colors_list.append({
                    "id": str(v.id),
                    "name": v.color_name,
                    "hex_code": v.color_hex,
                })
        return colors_list


class ProductFaq(TimeStampedModel):
    """Auxiliary customer support question/answer configurations."""

    product = models.ForeignKey(
        "product.Product",
        on_delete=models.CASCADE,
        related_name="faqs",
        null=True,
        blank=True,
    )
    question = models.CharField(max_length=300)
    answer = models.TextField()

    class Meta:
        verbose_name = _("Product FAQ")
        verbose_name_plural = _("Product FAQs")

    def __str__(self) -> str:
        return self.question


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 3: SIZING & FABRIC CONFIGURATIONS
# ─────────────────────────────────────────────────────────────────────────────

class ProductSizeAndMeasurementGuide(TimeStampedModel):
    """Reusable size-guide configurations and custom-fit ranges.

    Maintains standard size labels alongside raw measurement parameters (chest,
    waist, hip size metrics etc.) to avoid high manual data entry overhead [1].
    """

    vendor = models.ForeignKey(
        "vendor.VendorProfile",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="measurement_templates",
    )
    name = models.CharField(max_length=120, help_text="e.g. 'Men Senator Fit Guide'")
    
    DESCRIPTION_CHOICES = [
        ("clothing", _("Clothing")),
        ("footwear", _("Footwear")),
        ("accessory", _("Accessory")),
        ("measurement", _("Measurement-Based")),
        ("custom", _("Custom")),
    ]
    description = models.CharField(
        max_length=20,
        choices=DESCRIPTION_CHOICES,
        default="custom",
    )
    is_default = models.BooleanField(default=False)
    save_as_template = models.BooleanField(default=True)
    
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
    )

    chest_cm = models.CharField(max_length=20, blank=True)
    waist_cm = models.CharField(max_length=20, blank=True)
    hip_cm = models.CharField(max_length=20, blank=True)
    length_cm = models.CharField(max_length=20, blank=True)
    shoulder_cm = models.CharField(max_length=20, blank=True)
    sleeve_cm = models.CharField(max_length=20, blank=True)
    inseam_cm = models.CharField(max_length=20, blank=True)
    foot_length_cm = models.CharField(max_length=20, blank=True)
    sort_order = models.PositiveSmallIntegerField(default=0)

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

    def __str__(self) -> str:
        return f" {self.size_label} : {self.name}"


class ProductFabricSpecification(TimeStampedModel):
    """Technical fabric configurations and care instructions."""

    CARE_CHOICES = [
        ("machine_wash", _("Machine Wash")),
        ("hand_wash", _("Hand Wash")),
        ("dry_clean", _("Dry Clean Only")),
        ("do_not_wash", _("Do Not Wash")),
        ("cold_wash", _("Cold Water Wash")),
        ("tumble_dry", _("Tumble Dry Low")),
        ("air_dry", _("Air Dry")),
        ("allow_all", _("Allow All")),
    ]

    product = models.OneToOneField(
        Product,
        on_delete=models.CASCADE,
        related_name="product_fabric_specification",
    )
    fabric_type = models.CharField(max_length=120, help_text="e.g. Cashmere Blend")
    care_instructions = models.CharField(
        max_length=20,
        choices=CARE_CHOICES,
        default="machine_wash",
    )
    is_organic = models.BooleanField(default=False)
    is_vegan = models.BooleanField(default=False)
    country_of_origin = models.CharField(max_length=80, blank=True)

    class Meta:
        verbose_name = _("Product Fabric Specification")
        verbose_name_plural = _("Product Fabric Specifications")

    def __str__(self) -> str:
        return f"{self.fabric_type} - {self.country_of_origin}"


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 4: UNIFIED PRODUCTS VARIANTS & MEDIA
# ─────────────────────────────────────────────────────────────────────────────

class ProductVariantGalleryMedia(TimeStampedModel, SoftDeleteModel):
    """Consolidated model merging product variants and associated gallery media.

    Saves storage overhead and simplifies UI rendering by pairing sizes, colors,
    barcodes, and pricing overrides directly with Cloudinary media assets [1].
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
        help_text="Variant-specific Stock Keeping Unit identifier.",
    )
    size = models.ForeignKey(
        ProductSizeAndMeasurementGuide,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="product_size_variants",
    )
    color_name = models.CharField(max_length=100, blank=True)
    color_hex = models.CharField(
        max_length=7,
        blank=True,
        help_text="Visual swatch hex key. e.g. #FDA600",
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
    is_primary = models.BooleanField(
        default=False,
        help_text="Specifies if this asset serves as the primary catalog listing cover.",
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
        ordering = ["ordering", "created_at"]

    def __str__(self) -> str:
        parts = [self.product.title]
        if self.size:
            parts.append(self.size.size_label)
        if self.color_name:
            parts.append(self.color_name)
        return " / ".join(parts)

    def save(self, *args: Any, **kwargs: Any) -> None:
        """
        Unique SKU identifier generated automatically upon saving.
        is BEEN SHIFTED AND ADDED STRAIGHT TO THE PRODUCTVARIANTGALLERYMEDIA MODEL
        SO THAT EACH PRODUCT VARIANTS CAN HAVE THEIR OWN UNIQUE SKU
        ENDING WITH THEIR UNIQUE COLOR NAME AND SIZE.
        """
        if not self.sku:
            import uuid as _uuid

            # Use random uuid4 suffix to avoid UNIQUE collisions on rapid creation
            for _attempt in range(5):
                candidate = f"FASTAR-{_uuid.uuid4().hex[:8].upper()}"
                if not ProductVariantGalleryMedia.objects.filter(sku=candidate).exists():
                    self.sku = candidate
                    break
            else:
                self.sku = f"FASTAR-{_uuid.uuid4().hex[:12].upper()}"
        super().save(*args, **kwargs)


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 5: LOGISTICS & SHIPPING PROFILES
# ─────────────────────────────────────────────────────────────────────────────

class ProductShippingProfile(TimeStampedModel):
    """Volumetric package weight and dimension logistics parameters.

    Provides shipping calculator inputs and preferred courier listings.
    """

    vendor = models.ForeignKey(
        "vendor.VendorProfile",
        on_delete=models.CASCADE,
        related_name="vendor_shipping_profiles",
    )

    weight_kg = models.DecimalField(
        max_digits=7,
        decimal_places=3,
        default=0,
    )
    dimensions_cm = models.JSONField(null=True, blank=True)
    length_cm = models.DecimalField(max_digits=6, decimal_places=1, default=0)
    width_cm = models.DecimalField(max_digits=6, decimal_places=1, default=0)
    height_cm = models.DecimalField(max_digits=6, decimal_places=1, default=0)
    is_fragile = models.BooleanField(default=False)
    requires_signature = models.BooleanField(default=False)
    restricted_countries = models.JSONField(default=list, blank=True)
    preferred_couriers = models.ManyToManyField(
        DeliveryCourier,
        blank=True,
        related_name="preferred_shipping_products",
    )
    free_shipping_threshold = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Overrides platform default shipping configuration limits.",
    )
    processing_days = models.PositiveSmallIntegerField(default=1)

    @property
    def effective_free_shipping_threshold(self) -> Decimal:
        """Resolves active free shipping parameters with platform fallback."""
        if self.free_shipping_threshold is not None:
            return self.free_shipping_threshold
        try:
            from apps.global_platform_settings.cache import get_platform_settings

            settings = get_platform_settings()
            return settings.default_free_shipping_threshold
        except Exception:
            # Keep model access safe during migrations, shell imports, and tests.
            pass
        return Decimal("50000.00")

    class Meta:
        verbose_name = _("Product Shipping Profile")
        verbose_name_plural = _("Product Shipping Profiles")

    def __str__(self) -> str:
        product = getattr(self, "product_shipping_profiles", None)
        title = product.title if product else "Unlinked Profile"
        return f"{title} — {self.weight_kg}kg"



# ─────────────────────────────────────────────────────────────────────────────
# SECTION 6: FINANCIALS & POLICY TRACKING
# ─────────────────────────────────────────────────────────────────────────────

class ProductCommissionSnapshot(TimeStampedModel):
    """Administrative commission tracking ledger configurations."""

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

    def __str__(self) -> str:
        return f"{self.product.title} @ {self.commission_rate}%"


class Coupon(TimeStampedModel, SoftDeleteModel):
    """Discount coupon parameter structures."""

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
    usage_limit = models.PositiveIntegerField(null=True, blank=True)
    usage_count = models.PositiveIntegerField(default=0)
    vendor = models.ForeignKey(
        "vendor.VendorProfile",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="vendor_platform_wide_coupons",
    )
    product = models.ForeignKey(
        Product,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="product_specific_coupon",
    )
    active = models.BooleanField(default=True)
    valid_from = models.DateTimeField()
    valid_to = models.DateTimeField()

    class Meta:
        verbose_name = _("Coupon")
        verbose_name_plural = _("Coupons")

    def __str__(self) -> str:
        return f"{self.code} ({self.discount_type}: {self.discount_value})"

    def is_valid(self) -> bool:
        """Determines active date duration limits and coupon validation rules."""
        now_time = now()
        expired = now_time > self.valid_to
        usage_exhausted = (
            self.usage_limit is not None and self.usage_count >= self.usage_limit
        )
        return (
            self.active and not expired and not usage_exhausted and not self.is_deleted
        )


class ProductPriceHistory(TimeStampedModel):
    """Immutable price historical log ledger track mappings."""

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

    def __str__(self) -> str:
        if self.old_price:
            return f"{self.product.title}: {self.old_price} → {self.new_price} ({self.currency})"
        return f"{self.product.title}: Listed at {self.new_price} ({self.currency})"


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 7: LEDGERS & CUSTOMER REVIEW TRACKERS
# ─────────────────────────────────────────────────────────────────────────────

class ProductInventoryLog(TimeStampedModel):
    """Immutable transaction-safe stock adjustment metrics ledger logging [1]."""

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
        ProductVariantGalleryMedia,
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
    quantity_delta = models.IntegerField()
    quantity_before = models.PositiveIntegerField()
    quantity_after = models.PositiveIntegerField()
    reason = models.CharField(max_length=20, choices=REASON_CHOICES)
    reference_id = models.CharField(max_length=100, blank=True)
    note = models.TextField(blank=True)

    class Meta:
        verbose_name = _("Inventory Log")
        verbose_name_plural = _("Inventory Logs")
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.product.title} {self.quantity_delta:+d} ({self.reason})"


class ProductReview(TimeStampedModel, SoftDeleteModel):
    """Tailor and design assessment review feedback from validated shoppers."""

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
    reviewer_name = models.CharField(max_length=150, blank=True)
    reviewer_email = models.EmailField(blank=True)
    rating = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)],
    )
    review = models.TextField()
    reply = models.TextField(blank=True)
    active = models.BooleanField(default=True)
    moderated = models.BooleanField(default=False)
    helpful_votes = models.PositiveIntegerField(default=0)
    idempotency_key = models.UUIDField(null=True, blank=True, db_index=True)

    class Meta:
        verbose_name = _("Product Review")
        verbose_name_plural = _("Product Reviews")
        ordering = ["-created_at"]
        unique_together = [("product", "user")]

    def __str__(self) -> str:
        return f"{self.product.title} — {self.rating}★"

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Saves static user identification backups to protect history from account deletes."""
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


class ProductViewLog(TimeStampedModel):
    """Asynchronous analytical click tracker for dynamic recommendations."""

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
    )
    session_key = models.CharField(max_length=40, blank=True, db_index=True)
    referrer_url = models.CharField(max_length=500, blank=True)
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

    def __str__(self) -> str:
        actor = self.user.email if self.user else f"anon:{self.session_key[:8]}"
        return f"{self.product.title} viewed by {actor}"


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 8: PERSISTENCE & WISHLIST TRACKERS
# ─────────────────────────────────────────────────────────────────────────────





class ProductWishlist(TimeStampedModel):
    """Anonymous and logged-in client wishlist configurations."""

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

    def __str__(self) -> str:
        actor = self.user or f"anon:{self.session_key}"
        return f"{actor} ♥ {self.product.title}"
