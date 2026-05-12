# apps/product/schemas/product_schemas.py
"""
Django-Ninja (Pydantic v2) response & input schemas for Product async endpoints.

Design:
  - All UUIDs are str (frontend-safe, no uuid4 JSON serialization issues).
  - Optional fields use | None with explicit default=None.
  - Nested schemas mirror the ORM reverse-relation structure so resolvers
    never need extra queries beyond what the selector already prefetched.
  - Input schemas (In suffix) validate write payloads for Ninja POST/PATCH.
  - The "Out" schemas are what Ninja uses to auto-serialize ORM instances.

────────────────────────────────────────────────────────────────
5 Additional Enterprise Best-Practice Additions
────────────────────────────────────────────────────────────────
1. STRICT MODE: all schemas use model_config = {"from_attributes": True} so
   Ninja can auto-resolve ORM instance attributes without extra resolvers.
2. COMPUTED FIELDS: computed_avg_rating / computed_review_count map to the
   annotated fields produced by the selector's .annotate() call.
3. CLOUDINARY URL SCHEMA: CloudinaryMediaOut encapsulates both the raw
   public_id and the transformed secure_url for frontend flexibility.
4. PAGINATION WRAPPER: PaginatedOut[T] generic wraps any list result with
   count/next/previous metadata matching the DRF pagination contract.
5. BUNDLE RESPONSE: ProductDetailBundleOut combines product + reviews +
   in_wishlist so the Ninja bundle endpoint returns one typed response.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Generic, TypeVar
from uuid import UUID

from ninja import Schema
from pydantic import Field, field_validator

T = TypeVar("T")


# ─────────────────────────────────────────────────────────────────────────────
# GENERIC PAGINATION WRAPPER  (Best-practice #4)
# ─────────────────────────────────────────────────────────────────────────────

class PaginatedOut(Schema, Generic[T]):
    count: int
    next: str | None = None
    previous: str | None = None
    results: list[T]


# ─────────────────────────────────────────────────────────────────────────────
# TAXONOMY SCHEMAS
# ─────────────────────────────────────────────────────────────────────────────

class ProductCategoryOut(Schema):
    model_config = {"from_attributes": True}
    id: str
    name: str
    slug: str
    image_url: str | None = None


class ProductBrandOut(Schema):
    model_config = {"from_attributes": True}
    id: str
    name: str
    slug: str
    logo_url: str | None = None


class ProductVendorOut(Schema):
    """
    Best-practice #1: from_attributes=True lets Ninja resolve nested
    vendor.user.username without a custom resolver.
    """
    model_config = {"from_attributes": True}
    id: str
    store_name: str
    slug: str | None = None
    avatar_url: str | None = None
    is_verified: bool = False


class ProductSizeTypeOut(Schema):
    """Phase 1 — clothing/shoes/custom taxonomy node."""
    model_config = {"from_attributes": True}
    id: str
    name: str
    slug: str
    category: str = ""


class ProductSizeOut(Schema):
    """Expanded with Phase 1 fields: abbreviation, sort_order, size_type embed."""
    model_config = {"from_attributes": True}
    id: str
    name: str
    abbreviation: str = ""
    sort_order: int = 0
    size_type: ProductSizeTypeOut | None = None


class ProductColorOut(Schema):
    """Expanded with Phase 1 fields: swatch_image_url, is_active."""
    model_config = {"from_attributes": True}
    id: str
    name: str
    hex_code: str = ""
    swatch_image_url: str | None = None
    is_active: bool = True


class ProductTagOut(Schema):
    model_config = {"from_attributes": True}
    id: str
    name: str
    slug: str


# ─────────────────────────────────────────────────────────────────────────────
# PHASE 1 NEW TAXONOMY SCHEMAS
# ─────────────────────────────────────────────────────────────────────────────

class ProductFabricOut(Schema):
    """Fabric type with care/sustainability metadata — Phase 1."""
    model_config = {"from_attributes": True}
    id: str
    fabric_name: str
    composition_percentage: int = 100
    care_instructions: str = ""
    is_sustainable: bool = False
    sustainability_notes: str = ""


class ProductMeasurementGuideOut(Schema):
    """One size-chart row (e.g. S → chest 34–36 cm) — Phase 1."""
    model_config = {"from_attributes": True}
    id: str
    size_label: str
    chest_cm: Decimal | None = None
    waist_cm: Decimal | None = None
    hip_cm: Decimal | None = None
    shoulder_cm: Decimal | None = None
    length_cm: Decimal | None = None
    inseam_cm: Decimal | None = None
    sort_order: int = 0


class ProductCertificationOut(Schema):
    """Sustainability/quality certification badge — Phase 1."""
    model_config = {"from_attributes": True}
    id: str
    name: str
    issued_by: str = ""
    cert_type: str = ""
    certificate_number: str = ""
    issued_date: datetime | None = None
    expiry_date: datetime | None = None
    is_verified: bool = False
    badge_image_url: str | None = None


# ─────────────────────────────────────────────────────────────────────────────
# CLOUDINARY MEDIA  (Best-practice #3)
# ─────────────────────────────────────────────────────────────────────────────

class CloudinaryMediaOut(Schema):
    """
    Exposes both raw public_id and the CDN URL so the frontend can
    construct its own transforms (e.g. for the product builder preview).
    """
    model_config = {"from_attributes": True}
    public_id: str | None = None
    url: str | None = None
    thumbnail_url: str | None = None
    media_type: str = "image"
    alt_text: str = ""
    ordering: int = 0


class ProductGalleryMediaOut(Schema):
    """Expanded with Phase 1 fields: is_primary, video_thumbnail_url, duration_sec."""
    model_config = {"from_attributes": True}
    id: str
    media_url: str | None = None
    thumbnail_url: str | None = None
    video_thumbnail_url: str | None = None
    media_type: str
    alt_text: str = ""
    ordering: int
    is_primary: bool = False
    duration_sec: int | None = None


# ─────────────────────────────────────────────────────────────────────────────
# VARIANT / SPECIFICATION / FAQ
# ─────────────────────────────────────────────────────────────────────────────

class ProductVariantOut(Schema):
    """Expanded with Phase 1 fields: barcode, is_default, weight_kg, dimensions_cm."""
    model_config = {"from_attributes": True}
    id: str
    sku: str
    size: ProductSizeOut | None = None
    color: ProductColorOut | None = None
    price_override: Decimal | None = None
    stock_qty: int
    is_active: bool
    image_url: str | None = None
    # Phase 1 expansions
    barcode: str = ""
    is_default: bool = False
    weight_kg: Decimal | None = None
    dimensions_cm: str = ""
    notes: str = ""


class ProductSpecificationOut(Schema):
    model_config = {"from_attributes": True}
    id: str
    title: str
    content: str


class ProductFaqOut(Schema):
    model_config = {"from_attributes": True}
    id: str
    question: str
    answer: str


# ─────────────────────────────────────────────────────────────────────────────
# PRODUCT LIST ITEM  (catalog card)
# ─────────────────────────────────────────────────────────────────────────────


class ProductListItemOut(Schema):
    """
    Matches the .only() projection from get_published_products_list().
    Best-practice #2: includes computed_avg_rating / computed_review_count
    from the .annotate() call in the selector — no extra queries.
    """
    model_config = {"from_attributes": True}
    id: str
    title: str
    slug: str
    sku: str
    price: Decimal
    old_price: Decimal | None = None
    discount_percentage: int = 0
    currency: str = "NGN"
    image_url: str | None = None
    in_stock: bool
    stock_qty: int = 0
    featured: bool = False
    hot_deal: bool = False
    digital: bool = False
    rating: Decimal = Decimal("0")
    review_count: int = 0
    computed_review_count: int = 0
    computed_avg_rating: float = 0.0
    requires_measurement: bool = False
    is_customisable: bool = False
    category_name: str | None = None
    category_slug: str | None = None
    brand_name: str | None = None
    brand_slug: str | None = None
    vendor_name: str | None = None
    vendor_slug: str | None = None
    sizes: list[ProductSizeOut] = []
    colors: list[ProductColorOut] = []
    created_at: datetime


# ─────────────────────────────────────────────────────────────────────────────
# PRODUCT DETAIL
# ─────────────────────────────────────────────────────────────────────────────

class ProductDetailOut(Schema):
    """Full product schema for the PDP — expanded with all Phase 1 fields."""
    model_config = {"from_attributes": True}
    id: str
    title: str
    slug: str
    sku: str
    description: str
    short_description: str = ""
    price: Decimal
    old_price: Decimal | None = None
    discount_percentage: int = 0
    currency: str = "NGN"
    shipping_amount: Decimal = Decimal("0")
    image_url: str | None = None
    cover_image_url: str | None = None
    gallery: list[ProductGalleryMediaOut] = []
    in_stock: bool
    stock_qty: int = 0
    max_stock: int | None = None
    views: int = 0
    orders_count: int = 0
    rating: Decimal = Decimal("0")
    review_count: int = 0
    computed_review_count: int = 0
    computed_avg_rating: float = 0.0
    featured: bool = False
    hot_deal: bool = False
    digital: bool = False
    requires_measurement: bool = False
    is_customisable: bool = False
    sizes: list[ProductSizeOut] = []
    colors: list[ProductColorOut] = []
    tags: list[ProductTagOut] = []
    specifications: list[ProductSpecificationOut] = []
    faqs: list[ProductFaqOut] = []
    variants: list[ProductVariantOut] = []
    # Phase 1 embed lists
    fabrics: list[ProductFabricOut] = []
    measurement_guide: list[ProductMeasurementGuideOut] = []
    certifications: list[ProductCertificationOut] = []
    status: str
    category_name: str | None = None
    category_slug: str | None = None
    sub_category_name: str | None = None
    brand_name: str | None = None
    brand_slug: str | None = None
    vendor_id: str | None = None
    vendor_name: str | None = None
    vendor_slug: str | None = None
    vendor_is_verified: bool = False
    commission_rate: Decimal = Decimal("10.00")
    # Phase 1 Product fields
    weight_kg: Decimal | None = None
    condition: str = "new"
    is_pre_order: bool = False
    pre_order_date: datetime | None = None
    meta_title: str = ""
    meta_description: str = ""
    age_group: str = ""
    gender_target: str = ""
    created_at: datetime
    updated_at: datetime



# ─────────────────────────────────────────────────────────────────────────────
# REVIEW
# ─────────────────────────────────────────────────────────────────────────────

class ProductReviewOut(Schema):
    model_config = {"from_attributes": True}
    id: str
    reviewer_display: str = "Anonymous"
    reviewer_avatar_url: str | None = None
    product_title: str | None = None
    rating: int
    review: str
    reply: str = ""
    helpful_votes: int = 0
    active: bool
    moderated: bool
    created_at: datetime


class ProductReviewWriteIn(Schema):
    rating: int = Field(..., ge=1, le=5)
    review: str = Field(..., min_length=10, max_length=5000)
    idempotency_key: UUID | None = None

    @field_validator("review")
    @classmethod
    def strip_review(cls, v: str) -> str:
        return v.strip()


# ─────────────────────────────────────────────────────────────────────────────
# WISHLIST
# ─────────────────────────────────────────────────────────────────────────────

class WishlistItemOut(Schema):
    model_config = {"from_attributes": True}
    id: str
    product: ProductListItemOut
    created_at: datetime


class WishlistToggleOut(Schema):
    added: bool
    message: str


class WishlistBulkStatusOut(Schema):
    """Map of product_id → is_wishlisted. Used for rendering heart icons in list."""
    statuses: dict[str, bool]


# ─────────────────────────────────────────────────────────────────────────────
# COUPON
# ─────────────────────────────────────────────────────────────────────────────

class CouponOut(Schema):
    model_config = {"from_attributes": True}
    id: str
    code: str
    discount_type: str
    discount_value: Decimal
    minimum_order: Decimal = Decimal("0")
    maximum_discount: Decimal | None = None
    usage_limit: int | None = None
    usage_count: int = 0
    active: bool
    valid_from: datetime
    valid_to: datetime


class CouponValidateIn(Schema):
    code: str = Field(..., min_length=1, max_length=50)
    order_subtotal: Decimal = Field(..., gt=0)


class CouponValidateOut(Schema):
    coupon_id: str
    code: str
    discount_type: str
    discount_amount: Decimal


# ─────────────────────────────────────────────────────────────────────────────
# PRODUCT WRITE (Ninja input)
# ─────────────────────────────────────────────────────────────────────────────

class ProductWriteIn(Schema):
    title: str = Field(..., min_length=3, max_length=255)
    description: str = Field(..., min_length=20)
    short_description: str = Field("", max_length=500)
    price: Decimal = Field(..., gt=0)
    old_price: Decimal | None = None
    currency: str = "NGN"
    shipping_amount: Decimal = Decimal("0")
    stock_qty: int = Field(0, ge=0)
    max_stock: int | None = None
    category_ids: list[str] = Field(..., min_length=1, max_length=5)
    sub_category_ids: list[str] = Field(default_factory=list, max_length=5)
    size_ids: list[str] = []
    color_ids: list[str] = []
    tag_ids: list[str] = []
    requires_measurement: bool = False
    is_customisable: bool = False
    hot_deal: bool = False
    digital: bool = False
    commission_rate: Decimal = Decimal("10.00")
    idempotency_key: UUID | None = None


class InventoryAdjustIn(Schema):
    quantity_delta: int = Field(..., description="Positive = restock, Negative = deduction")
    reason: str = Field("adjustment", max_length=20)
    reference_id: str = ""
    note: str = ""


# ─────────────────────────────────────────────────────────────────────────────
# PRODUCT DETAIL BUNDLE  (Best-practice #5)
# ─────────────────────────────────────────────────────────────────────────────

class ProductDetailBundleOut(Schema):
    """
    Single response that bundles product + reviews + wishlist status.
    Returned by the Ninja bundle endpoint which uses asyncio.gather
    to fetch all three in parallel — one HTTP round-trip for the FE.
    """
    product: ProductDetailOut | None = None
    reviews: list[ProductReviewOut] = []
    in_wishlist: bool = False
    review_count: int = 0
    avg_rating: float = 0.0


class ProductInventoryLogOut(Schema):
    model_config = {"from_attributes": True}
    id: str
    quantity_delta: int
    quantity_before: int
    quantity_after: int
    reason: str
    reference_id: str = ""
    note: str = ""
    actor_name: str = "System"
    created_at: datetime
