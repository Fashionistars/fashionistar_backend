"""Django-Ninja response schemas for catalog async read endpoints.

Schema Contract — Single Source of Truth:
  All public-facing API response shapes are defined here.
  Backend views return plain dicts (for speed); these Ninja schemas
  document and validate the OpenAPI contract.

Phase enrichment (2026-Q3):
  - CatalogCategoryOut: added `active`, `cloudinary_url`; removed `is_deleted`
  - CatalogCollectionOut: added `cloudinary_url`, `background_cloudinary_url`
  - HomepageProductCardOut: added rich fields (gender_target, age_group,
    condition, is_pre_order, orders_count, views, cloudinary_url)
  - HomepageBundleMetaOut: added `banners_count`
  - HomepageBundleOut: added `banners` list
"""

from __future__ import annotations

from datetime import datetime

from ninja import Schema


class CatalogCategoryOut(Schema):
    """Public catalog category payload.

    Note: `is_deleted` is intentionally excluded — internal admin flag.
    Only active (non-deleted) categories are returned by the selector.
    """

    id: str
    name: str
    title: str
    slug: str
    image: str | None
    image_url: str
    cloudinary_url: str | None = None
    active: bool
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
    cloudinary_url: str | None = None
    active: bool
    created_at: datetime
    updated_at: datetime


class CatalogCollectionOut(Schema):
    """Public merchandising collection payload.

    Collections belong to vendors (not products).
    """

    id: str
    name: str
    title: str
    slug: str
    sub_title: str
    description: str
    image: str | None
    image_url: str
    cloudinary_url: str | None = None
    background_image: str | None
    background_image_url: str
    background_cloudinary_url: str | None = None
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
# Phase 11 + Phase Enrich — Homepage Bundle Schemas
# GET /catalog/homepage/bundle/ (v2 — 6 sections)
# These Ninja schemas document the response shape of get_homepage_bundle_v2().
# The view returns plain dicts for speed; schemas are used for OpenAPI docs.
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

    Fields:
      - Monetary values formatted as '0.00' decimal strings.
      - cloudinary_url: Cloudinary-optimised card URL (w_480,h_480,c_fill).
        Use this as primary image src; fall back to image_url if None.
      - gender_target: 'men' | 'women' | 'unisex' | 'boys' | 'girls' | 'kids' | ''
      - age_group:    'adult' | 'teen' | 'child' | 'toddler' | 'infant' | ''
      - condition:    'new' | 'used' | 'refurbished'
      - is_pre_order: True if the item ships on a future date.
      - orders_count: Social proof — total fulfilled orders for this product.
      - views:        Social proof — total product page views.
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
    cloudinary_url: str | None = None
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
    # Demographic & product-type signals
    gender_target: str = ""
    age_group: str = ""
    condition: str = "new"
    is_pre_order: bool = False
    # Social proof signals
    orders_count: int = 0
    views: int = 0
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
    """Collection carousel card — serialized from .values() dict.

    Collections are for vendors. A vendor joins one or more collections
    to signal which fashion categories they specialise in.
    """
    id: str
    name: str
    title: str
    slug: str
    sub_title: str
    description: str
    image: str | None
    image_url: str
    cloudinary_url: str | None = None
    background_image: str | None
    background_image_url: str
    created_at: str | None


class HomepageCategoryCardOut(Schema):
    """Category grid card — serialized from .values() dict.

    Categories are for products — a product belongs to 1–15 categories.
    Only active (non-deleted) records are served; `active` conveys that explicitly.
    """
    id: str
    name: str
    title: str
    slug: str
    image: str | None
    image_url: str
    cloudinary_url: str | None = None
    active: bool = True
    created_at: str | None


class HomepageBannerCardOut(Schema):
    """CMS-managed hero banner card for the homepage carousel."""
    id: str
    slot: str
    title: str
    subtitle: str
    cta_text: str
    cta_url: str
    image_url: str | None
    mobile_image_url: str | None
    sort_order: int


class HomepageBundleMetaOut(Schema):
    """Row-count metadata embedded in every homepage bundle response."""
    collections_count: int
    categories_count: int
    products_count: int
    hot_deals_count: int
    reviews_count: int
    banners_count: int = 0


class HomepageBundleOut(Schema):
    """
    Full homepage data bundle — returned by GET /catalog/homepage/bundle/ (v2).

    All six sections are populated by a single asyncio.gather() call on the
    backend — 6 parallel DB queries, total latency <30ms p95.

    The frontend calls this endpoint once per RSC render (ISR: 300 s).

    Sections:
      collections      — vendor collection carousel (up to 10)
      categories       — product category grid (up to 10)
      featured_products — featured product cards (up to 10)
      hot_deals         — hot-deal product cards (up to 10)
      reviews           — public review cards (up to 8)
      banners           — CMS hero banners (up to 5)
    """
    collections: list[HomepageCollectionCardOut]
    categories: list[HomepageCategoryCardOut]
    featured_products: list[HomepageProductCardOut]
    hot_deals: list[HomepageProductCardOut]
    reviews: list[HomepageReviewCardOut]
    banners: list[HomepageBannerCardOut] = []
    meta: HomepageBundleMetaOut
