"""Django-Ninja response schemas for product async read endpoints."""

from __future__ import annotations

from datetime import datetime

from ninja import Schema


class ProductCategoryOut(Schema):
    id: str
    name: str
    slug: str


class ProductBrandOut(Schema):
    id: str
    name: str
    slug: str
    logo_url: str | None


class ProductVendorOut(Schema):
    id: str
    store_name: str
    slug: str
    avatar_url: str | None


class ProductSizeOut(Schema):
    id: str
    name: str
    abbreviation: str
    sort_order: int


class ProductColorOut(Schema):
    id: str
    name: str
    hex_code: str


class ProductTagOut(Schema):
    id: str
    name: str
    slug: str


class ProductGalleryMediaOut(Schema):
    id: str
    image_url: str
    media_type: str
    alt_text: str
    ordering: int


class ProductVariantOut(Schema):
    id: str
    sku: str
    size: ProductSizeOut | None
    color: ProductColorOut | None
    price_override: str | None
    stock: int
    is_active: bool


class ProductListItemOut(Schema):
    id: str
    slug: str
    title: str
    sku: str
    cover_image_url: str | None
    price: str
    old_price: str | None
    currency: str
    average_rating: float
    review_count: int
    requires_measurement: bool
    status: str
    is_featured: bool
    vendor: ProductVendorOut
    category: ProductCategoryOut


class ProductDetailOut(ProductListItemOut):
    description: str
    condition: str
    weight_kg: str | None
    brand: ProductBrandOut | None
    tags: list[ProductTagOut]
    sizes: list[ProductSizeOut]
    colors: list[ProductColorOut]
    gallery: list[ProductGalleryMediaOut]
    variants: list[ProductVariantOut]
    specifications: list[dict[str, str]]
    faqs: list[dict[str, str]]
    commission_rate: str
    stock_count: int
    views_count: int
    published_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ProductReviewOut(Schema):
    id: str
    reviewer_name: str
    reviewer_avatar: str | None
    rating: int
    comment: str
    vendor_reply: str | None
    helpful_count: int
    is_verified_purchase: bool
    created_at: datetime


class WishlistItemOut(Schema):
    id: str
    product: ProductListItemOut
    created_at: datetime


class CouponOut(Schema):
    id: str
    code: str
    coupon_type: str
    discount_value: str
    min_order_amount: str
    max_uses: int | None
    uses_count: int
    valid_from: datetime
    valid_until: datetime | None
    is_active: bool
