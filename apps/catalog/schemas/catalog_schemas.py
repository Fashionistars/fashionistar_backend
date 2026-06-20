"""Django-Ninja response schemas for catalog async read endpoints."""

from __future__ import annotations

from datetime import datetime

from ninja import Schema


class CatalogCategoryOut(Schema):
    """Public catalog category payload."""

    id: str
    name: str
    title: str
    slug: str
    image: str | None
    image_url: str
    is_deleted: bool
    created_at: datetime
    updated_at: datetime


class CatalogBrandOut(Schema):
    """Public catalog brand payload."""

    id: str
    name: str
    title: str
    slug: str
    description: str
    image: str | None
    image_url: str
    active: bool
    created_at: datetime
    updated_at: datetime


class CatalogCollectionOut(Schema):
    """Public merchandising collection payload."""

    id: str
    name: str
    title: str
    slug: str
    sub_title: str
    description: str
    image: str | None
    image_url: str
    background_image: str | None
    background_image_url: str
    created_at: datetime
    updated_at: datetime


class CatalogBlogPostOut(Schema):
    """Public catalog blog payload."""

    id: str
    author: str | None
    author_name: str
    category: str | None
    category_name: str
    title: str
    slug: str
    excerpt: str
    content: str
    featured_image: str | None
    image_url: str
    gallery_media: list[str] | None
    status: str
    tags: list[str]
    seo_title: str
    seo_description: str
    is_featured: bool
    published_at: datetime | None
    view_count: int
    created_at: datetime
    updated_at: datetime


# ═══════════════════════════════════════════════════════════════════════════════
# Phase 11 — Homepage Bundle Schemas (GET /catalog/homepage/)
# These Ninja schemas document the response shape of get_homepage_bundle().
# They are used for OpenAPI docs only — the view returns plain dicts for speed.
# ═══════════════════════════════════════════════════════════════════════════════

class HomepageSizeOut(Schema):
    """Size chip on a homepage product card."""
    id: str
    name: str


class HomepageColorOut(Schema):
    """Color chip on a homepage product card."""
    id: str
    name: str
    hex_code: str


class HomepageProductCardOut(Schema):
    """
    Compact product card for homepage featured / hot-deals sections.
    All monetary fields are formatted as '0.00' decimal strings.
    """
    id: str
    title: str
    slug: str
    sku: str
    price: str
    old_price: str | None
    discount_percentage: int
    currency: str
    image_url: str | None
    in_stock: bool
    stock_qty: int
    featured: bool
    hot_deal: bool
    rating: float
    review_count: int
    computed_review_count: int
    computed_avg_rating: float
    category_name: str | None
    category_slug: str | None
    vendor_name: str
    vendor_slug: str | None
    requires_measurement: bool
    is_customisable: bool
    sizes: list[HomepageSizeOut]
    colors: list[HomepageColorOut]
    created_at: str | None


class HomepageReviewCardOut(Schema):
    """Public review card for the homepage social-proof section."""
    id: str
    reviewer_name: str
    reviewer_avatar_url: str | None
    product_title: str | None
    product_slug: str | None
    rating: int
    review_text: str
    helpful_votes: int
    created_at: str | None


class HomepageCollectionCardOut(Schema):
    """Collection carousel card — serialized from .values() dict."""
    id: str
    name: str
    title: str
    slug: str
    sub_title: str
    description: str
    image: str | None
    image_url: str
    background_image: str | None
    background_image_url: str
    created_at: str | None


class HomepageCategoryCardOut(Schema):
    """Category grid card — serialized from .values() dict."""
    id: str
    name: str
    title: str
    slug: str
    image: str | None
    image_url: str
    is_deleted: bool
    created_at: str | None


class HomepageBundleMetaOut(Schema):
    """Row-count metadata embedded in every homepage bundle response."""
    collections_count: int
    categories_count: int
    products_count: int
    hot_deals_count: int
    reviews_count: int


class HomepageBundleOut(Schema):
    """
    Full homepage data bundle — returned by GET /catalog/homepage/.

    All five sections are populated by a single asyncio.gather() call on the
    backend — 5 parallel DB queries, total latency <30ms p95.

    The frontend calls this endpoint once per RSC render (ISR: 300 s),
    replacing the previous 5-separate-fetch pattern.
    """
    collections: list[HomepageCollectionCardOut]
    categories: list[HomepageCategoryCardOut]
    featured_products: list[HomepageProductCardOut]
    hot_deals: list[HomepageProductCardOut]
    reviews: list[HomepageReviewCardOut]
    meta: HomepageBundleMetaOut
