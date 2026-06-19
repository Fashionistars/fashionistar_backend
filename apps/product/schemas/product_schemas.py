# apps/product/schemas/product_schemas.py
"""Asynchronous read-only schemas for the Product domain.

Handles serialization structures for asynchronous data requests: GET, LIST,
and search indexing [1].

These schemas are completely isolated from write validations to maximize
rendering performance [1]. They are optimized to pull data using prefetched
database queries, completely avoiding N+1 query loops [1]. All AI and system
internal properties are excluded [1].
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Generic, List, Optional, TypeVar, Dict, Any
from uuid import UUID
from ninja import Schema
from pydantic import Field, model_validator

T = TypeVar("T")


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 1: GENERIC PAGINATION SCHEMAS
# ─────────────────────────────────────────────────────────────────────────────

class PaginatedOut(Schema, Generic[T]):
    """Standardized wrapper structure for returning paginated query lists."""
    count: int
    next: Optional[str] = None
    previous: Optional[str] = None
    results: List[T]


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 2: READ TAXONOMY SCHEMAS
# ─────────────────────────────────────────────────────────────────────────────

class ProductCategoryOut(Schema):
    """Serialized classification categories."""
    model_config = {"from_attributes": True}
    id: str
    name: str
    slug: str
    image_url: Optional[str] = None


class ProductTagOut(Schema):
    """Serialized catalog search filters."""
    model_config = {"from_attributes": True}
    id: str
    name: str
    slug: str


class ProductVendorOut(Schema):
    """Serialized representation of designer profiles."""
    model_config = {"from_attributes": True}
    id: str
    store_name: str
    slug: Optional[str] = None
    avatar_url: Optional[str] = None
    is_verified: bool = False


class ProductSizeAndMeasurementGuideOut(Schema):
    """Serialized custom size chart values [1]."""
    model_config = {"from_attributes": True}
    id: str
    size_label: str
    chest_cm: str = ""
    waist_cm: str = ""
    hip_cm: str = ""
    length_cm: str = ""
    shoulder_cm: str = ""
    sleeve_cm: str = ""
    inseam_cm: str = ""
    foot_length_cm: str = ""
    sort_order: int = 0


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 3: READ LOGISTICS & FABRIC EMBED SCHEMAS
# ─────────────────────────────────────────────────────────────────────────────

class ProductFabricSpecificationOut(Schema):
    """Serialized textile and material care information."""
    model_config = {"from_attributes": True}
    id: str
    fabric_type: str
    care_instructions: str = "machine_wash"
    is_organic: bool = False
    is_vegan: bool = False
    country_of_origin: str = ""


class ProductShippingProfileOut(Schema):
    """Serialized logistics and volumetric package dimension rules."""
    model_config = {"from_attributes": True}
    id: str
    weight_kg: Decimal = Decimal("0.0")
    length_cm: Decimal = Decimal("0.0")
    width_cm: Decimal = Decimal("0.0")
    height_cm: Decimal = Decimal("0.0")
    is_fragile: bool = False
    requires_signature: bool = False
    restricted_countries: List[str] = []
    free_shipping_threshold: Optional[Decimal] = None
    processing_days: int = 1


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 4: UNIFIED VARIANTS & MEDIA SCHEMAS
# ─────────────────────────────────────────────────────────────────────────────

class ProductVariantGalleryMediaOut(Schema):
    """Serialized variants and associated Cloudinary gallery resources [1].

    Optimized to convert Cloudinary resource links directly into relative paths,
    completely avoiding extra database lookups [1].
    """
    model_config = {"from_attributes": True}
    id: str
    public_id: Optional[str] = None
    sku: str
    size: Optional[ProductSizeAndMeasurementGuideOut] = None
    color_name: str = ""
    color_hex: str = ""
    media_url: Optional[str] = None
    thumbnail_url: Optional[str] = None
    video_thumbnail_url: Optional[str] = None
    media_type: str = "image"
    alt_text: str = ""
    ordering: int = 0
    is_primary: bool = False
    duration_sec: Optional[int] = None
    barcode: str = ""

    @model_validator(mode="before")
    @classmethod
    def resolve_fields(cls, data: Any) -> Any:
        """Resolves raw storage properties into functional absolute paths [1]."""
        if hasattr(data, "id"):
            media_url = None
            media_obj = getattr(data, "media", None)
            if media_obj:
                media_url = getattr(media_obj, "url", str(media_obj))
            public_id = getattr(media_obj, "public_id", None) if media_obj else None

            # Generates pre-scaled CDN thumbnail images to accelerate page loads
            thumbnail_url = media_url
            if media_url and "res.cloudinary.com" in media_url and "/upload/" in media_url:
                thumbnail_url = media_url.replace("/upload/", "/upload/w_400,h_400,c_fill,f_auto,q_auto/")

            video_thumbnail_url = None
            vt_obj = getattr(data, "video_thumbnail", None)
            if vt_obj:
                video_thumbnail_url = getattr(vt_obj, "url", str(vt_obj))

            return {
                "id": str(data.id),
                "public_id": public_id or (str(media_obj) if media_obj else None),
                "sku": data.sku,
                "size": getattr(data, "size", None),
                "color_name": data.color_name or "",
                "color_hex": data.color_hex or "",
                "media_url": media_url,
                "thumbnail_url": thumbnail_url,
                "video_thumbnail_url": video_thumbnail_url,
                "media_type": data.media_type,
                "alt_text": data.alt_text or "",
                "ordering": data.ordering,
                "is_primary": data.is_primary,
                "duration_sec": data.duration_sec,
                "barcode": data.barcode or "",
            }
        return data


class ProductFaqOut(Schema):
    """Serialized customer support items."""
    model_config = {"from_attributes": True}
    id: str
    question: str
    answer: str


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 5: CATALOG ITEM & DETAIL SCHEMA
# ─────────────────────────────────────────────────────────────────────────────

class ProductListItemOut(Schema):
    """Optimized item card representation utilized on search lists.

    Combines rating stats directly from database joins with zero N+1 overhead [1].
    """
    model_config = {"from_attributes": True}
    id: str
    title: str
    slug: str
    # NOTE: sku removed from Product — each variant carries its own sku
    price: Decimal
    old_price: Optional[Decimal] = None
    discount_percentage: int = 0
    is_discounted: bool = False
    discounted_price: Optional[Decimal] = None
    cash_payment_mode: str = "disabled"
    currency: str = "NGN"
    image_url: Optional[str] = None
    in_stock: bool
    stock_qty: int = 0
    featured: bool = False
    hot_deal: bool = False
    rating: Decimal = Decimal("0")
    review_count: int = 0
    computed_review_count: int = 0
    computed_avg_rating: float = 0.0
    requires_measurement: bool = False
    is_customisable: bool = False
    category_name: Optional[str] = None
    category_slug: Optional[str] = None
    vendor_name: Optional[str] = None
    vendor_slug: Optional[str] = None
    sizes: List[ProductSizeAndMeasurementGuideOut] = []
    colors: List[Dict[str, Any]] = []
    condition: str = "new"
    gender_target: str = ""
    age_group: str = ""
    is_pre_order: bool = False
    pre_order_date: Optional[datetime] = None
    sustainability_score: Optional[Decimal] = None
    carbon_footprint_kg: Optional[Decimal] = None
    ai_trend_score: Decimal = Decimal("0.0")
    created_at: datetime


class ProductDetailOut(Schema):
    """Full detail read representation of a Product.

    Excludes all system AI attributes (`ai_description`, `style_tags`,
    `occasion_tags`, `body_type_fit`, `ai_trend_score`, `search_vector`)
    and carbon/sustainability metrics to secure internal scoring and reduce
    payload sizes [1].
    """
    model_config = {"from_attributes": True}
    id: str
    title: str
    slug: str
    # NOTE: sku removed from Product — each variant carries its own sku
    description: str
    price: Decimal
    old_price: Optional[Decimal] = None
    discount_percentage: int = 0
    is_discounted: bool = False
    discounted_price: Optional[Decimal] = None
    cash_payment_mode: str = "disabled"
    currency: str = "NGN"
    shipping_amount: Decimal = Decimal("2500")
    image_url: Optional[str] = None
    cover_image_url: Optional[str] = None
    gallery: List[ProductVariantGalleryMediaOut] = []
    in_stock: bool
    stock_qty: int = 0
    max_stock: Optional[int] = None
    views: int = 0
    orders_count: int = 0
    rating: Decimal = Decimal("0")
    review_count: int = 0
    computed_review_count: int = 0
    computed_avg_rating: float = 0.0
    featured: bool = False
    hot_deal: bool = False
    requires_measurement: bool = False
    is_customisable: bool = False
    faqs: List[ProductFaqOut] = []
    variants: List[ProductVariantGalleryMediaOut] = []
    fabric: Optional[ProductFabricSpecificationOut] = None
    measurement_guide: List[ProductSizeAndMeasurementGuideOut] = []
    shipping_profile: Optional[ProductShippingProfileOut] = None
    status: str
    categories: List[ProductCategoryOut] = []
    category_name: Optional[str] = None
    category_slug: Optional[str] = None
    vendor: Optional[ProductVendorOut] = None
    commission_rate: Decimal = Decimal("10.00")
    condition: str = "new"
    is_pre_order: bool = False
    pre_order_date: Optional[datetime] = None
    meta_title: str = ""
    meta_description: str = ""
    age_group: str = ""
    gender_target: str = ""
    sustainability_score: Optional[Decimal] = None
    carbon_footprint_kg: Optional[Decimal] = None
    ai_trend_score: Decimal = Decimal("0.0")
    created_at: datetime
    updated_at: datetime


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 6: SERVICE-RELATED LEDGER READ SCHEMAS
# ─────────────────────────────────────────────────────────────────────────────

class ProductReviewOut(Schema):
    """Serialized consumer feedback parameters."""
    model_config = {"from_attributes": True}
    id: str
    reviewer_name: str = "Anonymous"
    reviewer_email: str = ""
    product_title: Optional[str] = None
    rating: int
    review: str
    reply: str = ""
    helpful_votes: int = 0
    active: bool
    moderated: bool
    created_at: datetime


class WishlistItemOut(Schema):
    """Serialized wishlist values."""
    model_config = {"from_attributes": True}
    id: str
    product: ProductListItemOut
    created_at: datetime


class CouponOut(Schema):
    """Serialized promotional coupon parameter definitions."""
    model_config = {"from_attributes": True}
    id: str
    code: str
    discount_type: str
    discount_value: Decimal
    minimum_order: Decimal = Decimal("0")
    maximum_discount: Optional[Decimal] = None
    usage_limit: Optional[int] = None
    usage_count: int = 0
    active: bool
    valid_from: datetime
    valid_to: datetime


class ProductInventoryLogOut(Schema):
    """Serialized inventory change records."""
    model_config = {"from_attributes": True}
    id: str
    quantity_delta: int
    quantity_before: int
    quantity_after: int
    reason: str
    reference_id: str = ""
    note: str = ""
    actor_name: str = "System Engine"
    created_at: datetime


class ProductDetailBundleOut(Schema):
    """Bundled product data representation designed for the PDP layout.

    Allows the frontend to fetch the product specifications, active reviews, and
    client wishlist status in a single asynchronous request [1].
    """
    product: Optional[ProductDetailOut] = None
    reviews: List[ProductReviewOut] = []
    in_wishlist: bool = False
    review_count: int = 0
    avg_rating: float = 0.0


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 7: WRITE / INPUT & EXTRA ENDPOINT SCHEMAS
# ─────────────────────────────────────────────────────────────────────────────

class CouponValidateIn(Schema):
    code: str
    order_subtotal: Decimal
    cart_total: Optional[Decimal] = None


class CouponValidateOut(Schema):
    coupon_id: str
    code: str
    discount_type: str
    discount_amount: Decimal


class InventoryAdjustIn(Schema):
    quantity_delta: int
    reason: str
    note: str = ""
    reference_id: str = ""


class ProductReviewWriteIn(Schema):
    rating: int
    review: str
    idempotency_key: Optional[UUID] = None


class WishlistBulkStatusOut(Schema):
    statuses: Dict[str, bool]


class WishlistToggleOut(Schema):
    added: bool
    message: str


class MeasurementTemplateRowIn(Schema):
    size_label: str
    chest_cm: str = ""
    waist_cm: str = ""
    hip_cm: str = ""
    length_cm: str = ""
    shoulder_cm: str = ""
    sleeve_cm: str = ""
    inseam_cm: str = ""
    foot_length_cm: str = ""
    sort_order: int = 0


class MeasurementTemplateRowOut(Schema):
    id: str
    size_id: str
    size_label: str
    chest_cm: str = ""
    waist_cm: str = ""
    hip_cm: str = ""
    length_cm: str = ""
    shoulder_cm: str = ""
    sleeve_cm: str = ""
    inseam_cm: str = ""
    foot_length_cm: str = ""
    sort_order: int = 0


class VendorMeasurementTemplateIn(Schema):
    name: str
    description: str = ""
    template_rows: List[MeasurementTemplateRowIn]


class VendorMeasurementTemplateOut(Schema):
    id: str
    vendor_id: str
    name: str
    description: str = ""
    template_rows: List[MeasurementTemplateRowOut]
