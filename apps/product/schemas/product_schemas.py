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
from pydantic import Field, field_validator, model_validator

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



class ProductSizeAndMeasurementGuideOut(Schema):
    """Sizing schema mapped from ProductSizeAndMeasurementGuide."""
    model_config = {"from_attributes": True}
    id: str
    name: str
    abbreviation: str = ""
    sort_order: int = 0

    @model_validator(mode="before")
    @classmethod
    def resolve_from_attributes(cls, data: Any) -> Any:
        if hasattr(data, "size_label"):
            return {
                "id": str(data.id),
                "name": data.size_label,
                "abbreviation": data.size_label,
                "sort_order": data.sort_order,
            }
        return data


class ProductColorOut(Schema):
    id: str
    name: str
    hex_code: str = ""


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
    fabric_type: str
    composition: dict | list | None = None
    care_instructions: str = "machine_wash"
    care_notes: str = ""
    is_organic: bool = False
    is_vegan: bool = False
    country_of_origin: str = ""


class ProductFabricIn(Schema):
    fabric_type: str
    composition: dict | list | None = None
    care_instructions: str = "machine_wash"
    care_notes: str = ""
    is_organic: bool = False
    is_vegan: bool = False
    country_of_origin: str = ""


class ProductMeasurementGuideOut(Schema):
    """One size-chart row (e.g. S → chest 34–36 cm) — Phase 1."""
    model_config = {"from_attributes": True}
    id: str
    size_label: str
    chest_cm: str = ""
    waist_cm: str = ""
    hip_cm: str = ""
    shoulder_cm: str = ""
    sleeve_cm: str = ""
    length_cm: str = ""
    inseam_cm: str = ""
    foot_length_cm: str = ""
    sort_order: int = 0


class ProductMeasurementGuideIn(Schema):
    size_label: str
    chest_cm: str = ""
    waist_cm: str = ""
    hip_cm: str = ""
    shoulder_cm: str = ""
    sleeve_cm: str = ""
    length_cm: str = ""
    inseam_cm: str = ""
    foot_length_cm: str = ""
    sort_order: int = 0


class ProductShippingProfileOut(Schema):
    model_config = {"from_attributes": True}
    id: str
    weight_kg: Decimal = Decimal("0.0")
    length_cm: Decimal = Decimal("0.0")
    width_cm: Decimal = Decimal("0.0")
    height_cm: Decimal = Decimal("0.0")
    is_fragile: bool = False
    requires_signature: bool = False
    restricted_countries: list[str] = []
    free_shipping_threshold: Decimal | None = None
    processing_days: int = 1


class ProductShippingProfileIn(Schema):
    weight_kg: Decimal = Decimal("0.0")
    length_cm: Decimal = Decimal("0.0")
    width_cm: Decimal = Decimal("0.0")
    height_cm: Decimal = Decimal("0.0")
    is_fragile: bool = False
    requires_signature: bool = False
    restricted_countries: list[str] = []
    free_shipping_threshold: Decimal | None = None
    processing_days: int = 1
    template_id: str | None = None


class VendorMeasurementTemplateRowOut(Schema):
    model_config = {"from_attributes": True}
    id: str
    size_id: str | None = None
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


class VendorMeasurementTemplateOut(Schema):
    model_config = {"from_attributes": True}
    id: str
    vendor_id: str
    name: str
    description: str = ""
    template_rows: list[VendorMeasurementTemplateRowOut] = []


class VendorMeasurementTemplateRowIn(Schema):
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
    description: str = "custom"
    template_rows: list[VendorMeasurementTemplateRowIn] = []



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
    """Resolved from ProductVariantGalleryMedia."""
    model_config = {"from_attributes": True}
    id: str
    media_url: str | None = None
    thumbnail_url: str | None = None
    video_thumbnail_url: str | None = None
    media_type: str = "image"
    alt_text: str = ""
    ordering: int = 0
    is_primary: bool = False
    duration_sec: int | None = None
    variant_id: str | None = None
    color_name: str | None = None
    color_hex: str | None = None

    @model_validator(mode="before")
    @classmethod
    def resolve_gallery_fields(cls, data: Any) -> Any:
        if hasattr(data, "id"):
            variant_id = str(data.id) if getattr(data, "sku", None) else None
            media_url = str(data.media.url) if getattr(data, "media", None) else None
            thumbnail_url = media_url
            if media_url and "res.cloudinary.com" in media_url and "/upload/" in media_url:
                thumbnail_url = media_url.replace("/upload/", "/upload/w_400,h_400,c_fill,f_auto,q_auto/")
            
            video_thumbnail_url = str(data.video_thumbnail.url) if getattr(data, "video_thumbnail", None) else None
            
            return {
                "id": str(data.id),
                "media_url": media_url,
                "thumbnail_url": thumbnail_url,
                "video_thumbnail_url": video_thumbnail_url,
                "media_type": data.media_type,
                "alt_text": data.alt_text or "",
                "ordering": data.ordering,
                "is_primary": data.is_primary,
                "duration_sec": data.duration_sec,
                "variant_id": variant_id,
                "color_name": data.color_name,
                "color_hex": data.color_hex,
            }
        return data


# ─────────────────────────────────────────────────────────────────────────────
# VARIANT / SPECIFICATION / FAQ
# ─────────────────────────────────────────────────────────────────────────────

class ProductVariantOut(Schema):
    """Consolidated variant + gallery media schema — mirrors ProductVariantGalleryMedia exactly."""
    model_config = {"from_attributes": True}
    id: str
    sku: str
    size: ProductSizeAndMeasurementGuideOut | None = None
    color_name: str = ""
    color_hex: str = ""
    stock_qty: int = 0
    media_url: str | None = None
    media_type: str = "image"
    alt_text: str = ""
    ordering: int = 0
    is_primary: bool = False
    video_thumbnail_url: str | None = None
    duration_sec: int | None = None
    barcode: str = ""
    notes: str = ""

    @model_validator(mode="before")
    @classmethod
    def resolve_variant_fields(cls, data: Any) -> Any:
        if hasattr(data, "id"):
            media_url = str(data.media.url) if getattr(data, "media", None) else None
            video_thumbnail_url = str(data.video_thumbnail.url) if getattr(data, "video_thumbnail", None) else None
            return {
                "id": str(data.id),
                "sku": data.sku,
                "size": data.size,
                "color_name": data.color_name or "",
                "color_hex": data.color_hex or "",
                "stock_qty": data.stock_qty,
                "media_url": media_url,
                "media_type": data.media_type,
                "alt_text": data.alt_text or "",
                "ordering": data.ordering,
                "is_primary": data.is_primary,
                "video_thumbnail_url": video_thumbnail_url,
                "duration_sec": data.duration_sec,
                "barcode": data.barcode or "",
                "notes": data.notes or "",
            }
        return data


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
    sizes: list[ProductSizeAndMeasurementGuideOut] = []
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
    price: Decimal
    old_price: Decimal | None = None
    discount_percentage: int = 0
    currency: str = "NGN"
    shipping_amount: Decimal = Decimal("1000")
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
    sizes: list[ProductSizeAndMeasurementGuideOut] = []
    tags: list[ProductTagOut] = []
    specifications: list[ProductSpecificationOut] = []
    faqs: list[ProductFaqOut] = []
    variants: list[ProductVariantOut] = []
    # Phase 1 embeds
    fabric: ProductFabricOut | None = None
    measurement_guide: list[ProductMeasurementGuideOut] = []
    shipping_profile: ProductShippingProfileOut | None = None
    # certifications: list[ProductCertificationOut] = []
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
    measurement_template_id: str | None = None
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

class ProductVariantWriteIn(Schema):
    """Write payload for creating/updating a ProductVariantGalleryMedia row."""
    sku: str | None = None
    size_id: str | None = None
    color_name: str = ""
    color_hex: str = ""
    stock_qty: int = 0
    barcode: str = ""
    notes: str = ""
    media: str | None = None
    media_type: str = "image"
    alt_text: str = ""
    ordering: int = 0
    is_primary: bool = False
    video_thumbnail: str | None = None
    duration_sec: int | None = None


class ProductWriteIn(Schema):
    title: str = Field(..., min_length=3, max_length=255)
    description: str = Field(..., min_length=100)
    price: Decimal = Field(..., ge=5000)
    old_price: Decimal | None = Field(default=None, ge=5000)
    currency: str = "NGN"
    shipping_amount: Decimal = Decimal("2500")
    stock_qty: int = Field(0, ge=0)
    max_stock: int | None = None
    category_ids: list[str] = Field(..., min_length=1, max_length=15)
    sub_category_ids: list[str] = Field(default_factory=list, max_length=15)
    size_ids: list[str] = []
    # color_ids removed — colors are now stored directly via color_name/color_hex on variants
    tag_ids: list[str] = []
    requires_measurement: bool = False
    measurement_template_id: UUID | None = None
    is_customisable: bool = False
    hot_deal: bool = False
    digital: bool = False
    commission_rate: Decimal = Decimal("10.00")
    idempotency_key: UUID | None = None
    weight_kg: Decimal | None = None
    condition: str = "new"
    is_pre_order: bool = False
    pre_order_date: datetime | None = None
    meta_title: str = ""
    meta_description: str = ""
    age_group: str = ""
    gender_target: str = ""
    fabric: ProductFabricIn | None = None
    shipping_profile: ProductShippingProfileIn | None = None
    measurement_guide: list[ProductMeasurementGuideIn] = []
    variants: list[ProductVariantWriteIn] = []


class ProductDraftSessionOut(Schema):
    model_config = {"from_attributes": True}
    id: UUID
    draft_key: UUID
    idempotency_key: UUID | None = None
    payload: dict
    current_step: int
    status: str
    linked_product_id: UUID | None = None
    expires_at: datetime
    last_synced_at: datetime


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
