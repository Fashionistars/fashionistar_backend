"""Catalog Django-Ninja async read router — with Redis API caching.

Cache Strategy (Section 4 of apps/common/utils/redis.py):
  - api_cache_get / api_cache_set use Django's cache framework (django-redis backend).
  - IGNORE_EXCEPTIONS=True ensures cache outages degrade to DB fallback silently.
  - No retry loop — cache miss is instant, never blocks the response.
  - TTLs are intentionally short for mutable catalog data:
      categories / brands  → 5 min  (admin edits are infrequent)
      collections          → 5 min  (merchandising surfaces)
      blog posts           → 10 min (editorial content, lower mutation rate)
      homepage bundle      → 5 min  (composite of all catalog + product data)
  - Cache keys include page + page_size for correct per-page caching.
  - Write mutations (admin panel) MUST call api_cache_delete_pattern("catalog:*")
    to invalidate stale entries — currently handled via Django admin post-save signal.

Phase 11 — Homepage Bundle Endpoint:
  GET /catalog/homepage/ — fires 5 DB queries in parallel via asyncio.gather():
    1. CatalogSelector.aget_homepage_collections(limit=10)
    2. CatalogSelector.aget_homepage_categories(limit=10)
    3. aget_homepage_products(limit=10)
    4. aget_homepage_hot_deals(limit=10)
    5. aget_homepage_reviews(limit=8)

  Latency target: <30ms p95 (all queries run concurrently on PgBouncer pool).
  Cache key: catalog:homepage:bundle — 5 min TTL.
  The frontend calls this single endpoint instead of making 5 separate requests.
"""

from __future__ import annotations

import asyncio
import logging
from decimal import Decimal

from ninja import Router
from ninja.errors import HttpError

from apps.catalog.schemas import (
    CatalogBlogPostOut,
    CatalogBrandOut,
    CatalogCategoryOut,
    CatalogCollectionOut,
)
from apps.catalog.selectors import CatalogSelector
from apps.catalog.serializers.common import safe_media_url
from apps.common.pagination import async_ninja_paginate
from apps.common.utils.redis import api_cache_get, api_cache_set

logger = logging.getLogger(__name__)
router = Router(tags=["Catalog — Async Reads"])

# ── TTLs ────────────────────────────────────────────────────────────────────────
_TTL_CATALOG   = 5 * 60    # 5 minutes — categories, brands, collections
_TTL_BLOG      = 10 * 60   # 10 minutes — editorial content
_TTL_HOMEPAGE  = 5 * 60    # 5 minutes — homepage bundle (composite)


# ── Serialisers ─────────────────────────────────────────────────────────────────

def _category_out(category) -> dict:
    """Serialize a Category without DRF overhead."""

    image_url = safe_media_url(category, "image")
    return {
        "id": str(category.pk),
        "name": category.name,
        "title": category.name,
        "slug": category.slug or "",
        "image": str(category.image) if category.image else None,
        "image_url": image_url,
        "active": category.active,
        "created_at": category.created_at,
        "updated_at": category.updated_at,
    }


def _brand_out(brand) -> dict:
    """Serialize a Brand without DRF overhead."""

    image_url = safe_media_url(brand, "image")
    return {
        "id": str(brand.pk),
        "name": brand.title,
        "title": brand.title,
        "slug": brand.slug or "",
        "description": brand.description or "",
        "image": str(brand.image) if brand.image else None,
        "image_url": image_url,
        "active": brand.active,
        "created_at": brand.created_at,
        "updated_at": brand.updated_at,
    }


def _collection_out(collection) -> dict:
    """Serialize a Collection without DRF overhead."""

    image_url = safe_media_url(collection, "image")
    background_url = safe_media_url(collection, "background_image")
    return {
        "id": str(collection.pk),
        "name": collection.title or "",
        "title": collection.title or "",
        "slug": collection.slug or "",
        "sub_title": collection.sub_title or "",
        "description": collection.description or "",
        "image": str(collection.image) if collection.image else None,
        "image_url": image_url,
        "background_image": (
            str(collection.background_image) if collection.background_image else None
        ),
        "background_image_url": background_url,
        "created_at": collection.created_at,
        "updated_at": collection.updated_at,
    }


def _blog_out(post) -> dict:
    """Serialize a BlogPost without DRF overhead."""

    author = getattr(post, "author", None)
    category = getattr(post, "category", None)
    featured_image_url = safe_media_url(post, "featured_image")
    gallery_media = [
        safe_media_url(media, "image")
        for media in getattr(post, "gallery_media", []).all()
    ]
    author_name = "Fashionistar Editorial"
    if author:
        author_name = author.get_full_name() or getattr(author, "email", "") or str(author)

    return {
        "id": str(post.pk),
        "author": str(author.pk) if author else None,
        "author_name": author_name,
        "category": str(category.pk) if category else None,
        "category_name": getattr(category, "name", "") if category else "",
        "title": post.title,
        "slug": post.slug,
        "excerpt": post.excerpt or "",
        "content": post.content,
        "featured_image": str(post.featured_image) if post.featured_image else None,
        "featured_image_url": featured_image_url,
        "image_url": featured_image_url,
        "gallery_media": [url for url in gallery_media if url],
        "status": post.status,
        "tags": post.tags or [],
        "seo_title": post.seo_title or "",
        "seo_description": post.seo_description or "",
        "is_featured": post.is_featured,
        "published_at": post.published_at,
        "view_count": post.view_count,
        "created_at": post.created_at,
        "updated_at": post.updated_at,
    }


def _money(value) -> str:
    """Format Decimal/str/None as '0.00' money string."""
    if value is None:
        return "0.00"
    return f"{Decimal(str(value)):.2f}"


def _image_url_cloudinary(field, transform: str = "f_auto,q_auto") -> str | None:
    """Return a Cloudinary-optimised URL for a media field."""
    if not field:
        return None
    try:
        raw = str(field.url)
        if "res.cloudinary.com" in raw and "/upload/" in raw:
            return raw.replace("/upload/", f"/upload/{transform}/")
        return raw
    except (AttributeError, ValueError):
        return str(field) if field else None


def _homepage_product_out(product) -> dict:
    """
    Compact product card for the homepage — matches the contract of
    _product_card_out() in product_views.py but with cloudinary card transforms.
    Only reads from prefetch caches — zero extra queries.
    """
    raw_url = _image_url_cloudinary(product.image)
    card_url: str | None = None
    if raw_url and "res.cloudinary.com" in raw_url:
        card_url = raw_url.replace(
            "/upload/", "/upload/w_480,h_480,c_fill,f_auto,q_auto/"
        )
    else:
        card_url = raw_url

    # Read prefetch caches — NEVER call .all() on async-context M2M managers
    prefetch_cache = getattr(product, "_prefetched_objects_cache", {}) or {}
    prefetched_cats = prefetch_cache.get("categories", None)
    category = prefetched_cats[0] if prefetched_cats else None

    sizes = list(prefetch_cache.get("sizes", []))
    colors = list(prefetch_cache.get("colors", []))

    vendor = getattr(product, "vendor", None)
    vendor_name = "Fashionistar"
    vendor_slug = None
    if vendor:
        vendor_name = (
            getattr(vendor, "store_name", None)
            or getattr(vendor, "business_name", None)
            or str(vendor)
        )
        vendor_slug = getattr(vendor, "store_slug", None) or getattr(vendor, "slug", None)

    return {
        "id": str(product.pk),
        "title": product.title,
        "slug": product.slug,
        "sku": product.sku,
        "price": _money(product.price),
        "old_price": _money(product.old_price) if product.old_price else None,
        "discount_percentage": getattr(product, "discount_percentage", 0),
        "currency": product.currency,
        "image_url": card_url,
        "in_stock": product.in_stock,
        "stock_qty": product.stock_qty,
        "featured": product.featured,
        "hot_deal": product.hot_deal,
        "digital": product.digital,
        "rating": float(product.rating or 0),
        "review_count": product.review_count,
        "computed_review_count": getattr(product, "computed_review_count", 0),
        "computed_avg_rating": float(getattr(product, "computed_avg_rating", 0) or 0),
        "category_name": category.name if category else None,
        "category_slug": category.slug if category else None,
        "vendor_name": vendor_name,
        "vendor_slug": vendor_slug,
        "requires_measurement": product.requires_measurement,
        "is_customisable": product.is_customisable,
        "sizes": [{"id": str(s.pk), "name": s.name} for s in sizes],
        "colors": [
            {"id": str(c.pk), "name": c.name, "hex_code": c.hex_code or "#000000"}
            for c in colors
        ],
        "created_at": product.created_at.isoformat() if product.created_at else None,
    }


def _homepage_collection_from_dict(row: dict) -> dict:
    """
    Convert a .values() dict row (from aget_homepage_collections) to
    a serialized collection card — resolves image field to URL.
    """
    image_raw = row.get("image")
    bg_raw = row.get("background_image")
    # .values() rows contain raw ImageField paths — wrap via safe_media_url helper
    image_url = f"/media/{image_raw}" if image_raw else ""
    bg_url = f"/media/{bg_raw}" if bg_raw else ""
    return {
        "id": str(row["id"]),
        "name": row.get("title") or "",
        "title": row.get("title") or "",
        "slug": row.get("slug") or "",
        "sub_title": row.get("sub_title") or "",
        "description": row.get("description") or "",
        "image": image_raw or None,
        "image_url": image_url,
        "background_image": bg_raw or None,
        "background_image_url": bg_url,
        "created_at": row.get("created_at").isoformat() if row.get("created_at") else None,
    }


def _homepage_category_from_dict(row: dict) -> dict:
    """
    Convert a .values() dict row (from aget_homepage_categories) to
    a serialized category card.
    """
    image_raw = row.get("image")
    image_url = f"/media/{image_raw}" if image_raw else ""
    return {
        "id": str(row["id"]),
        "name": row.get("name") or "",
        "title": row.get("name") or "",
        "slug": row.get("slug") or "",
        "image": image_raw or None,
        "image_url": image_url,
        "active": row.get("active", True),
        "created_at": row.get("created_at").isoformat() if row.get("created_at") else None,
    }


async def _paginated(request, queryset, serializer, *, page: int, page_size: int) -> dict:
    """Apply the global Ninja paginator and serialize its result objects."""

    payload = await async_ninja_paginate(
        request,
        queryset,
        page=page,
        page_size=page_size,
        max_page_size=25,
    )
    payload["results"] = [serializer(item) for item in payload["results"]]
    return payload


# ── List endpoints (Redis-cached) ───────────────────────────────────────────────

@router.get("/categories/", auth=None)
async def list_categories(request, page: int = 1, page_size: int = 20):
    """Return active catalog categories.

    Cache: ``catalog:categories:{page}:{page_size}`` — 5 min TTL.
    Cache miss falls back to DB transparently.
    """
    cache_key = f"catalog:categories:{page}:{page_size}"
    cached = api_cache_get(cache_key)
    if cached is not None:
        return cached

    result = await _paginated(
        request,
        CatalogSelector.acategories(),
        _category_out,
        page=page,
        page_size=page_size,
    )
    api_cache_set(cache_key, result, ttl=_TTL_CATALOG)
    return result


@router.get("/categories/{slug}/", response=CatalogCategoryOut, auth=None)
async def get_category(request, slug: str):
    """Return one active category by slug."""

    category = await CatalogSelector.acategory_by_slug(slug)
    if category is None:
        raise HttpError(404, "Category not found.")
    return _category_out(category)


@router.get("/brands/", auth=None)
async def list_brands(request, page: int = 1, page_size: int = 20):
    """Return active catalog brands.

    Cache: ``catalog:brands:{page}:{page_size}`` — 5 min TTL.
    """
    cache_key = f"catalog:brands:{page}:{page_size}"
    cached = api_cache_get(cache_key)
    if cached is not None:
        return cached

    result = await _paginated(
        request,
        CatalogSelector.abrands(),
        _brand_out,
        page=page,
        page_size=page_size,
    )
    api_cache_set(cache_key, result, ttl=_TTL_CATALOG)
    return result


@router.get("/brands/{slug}/", response=CatalogBrandOut, auth=None)
async def get_brand(request, slug: str):
    """Return one active brand by slug."""

    brand = await CatalogSelector.abrand_by_slug(slug)
    if brand is None:
        raise HttpError(404, "Brand not found.")
    return _brand_out(brand)


@router.get("/collections/", auth=None)
async def list_collections(request, page: int = 1, page_size: int = 20):
    """Return merchandising collections.

    Cache: ``catalog:collections:{page}:{page_size}`` — 5 min TTL.
    """
    cache_key = f"catalog:collections:{page}:{page_size}"
    cached = api_cache_get(cache_key)
    if cached is not None:
        return cached

    result = await _paginated(
        request,
        CatalogSelector.acollections(),
        _collection_out,
        page=page,
        page_size=page_size,
    )
    api_cache_set(cache_key, result, ttl=_TTL_CATALOG)
    return result


@router.get("/collections/{slug}/", response=CatalogCollectionOut, auth=None)
async def get_collection(request, slug: str):
    """Return one merchandising collection by slug."""

    collection = await CatalogSelector.acollection_by_slug(slug)
    if collection is None:
        raise HttpError(404, "Collection not found.")
    return _collection_out(collection)


@router.get("/blog/", auth=None)
async def list_blog_posts(request, page: int = 1, page_size: int = 20):
    """Return published catalog blog posts.

    Cache: ``catalog:blog:{page}:{page_size}`` — 10 min TTL.
    """
    cache_key = f"catalog:blog:{page}:{page_size}"
    cached = api_cache_get(cache_key)
    if cached is not None:
        return cached

    result = await _paginated(
        request,
        CatalogSelector.ablog_posts(),
        _blog_out,
        page=page,
        page_size=page_size,
    )
    api_cache_set(cache_key, result, ttl=_TTL_BLOG)
    return result


@router.get("/blog/{slug}/", response=CatalogBlogPostOut, auth=None)
async def get_blog_post(request, slug: str):
    """Return one published catalog blog post by slug."""

    post = await CatalogSelector.ablog_post_by_slug(slug)
    if post is None:
        raise HttpError(404, "Blog post not found.")
    return _blog_out(post)


# ── Phase 11 — Homepage Bundle Endpoint ──────────────────────────────────────────

@router.get("/homepage/", auth=None, summary="Homepage data bundle — 5 parallel DB reads")
async def get_homepage_bundle(
    request,
    collections_limit: int = 10,
    categories_limit: int = 10,
    products_limit: int = 10,
    hot_deals_limit: int = 10,
    reviews_limit: int = 8,
):
    """
    Single endpoint that powers the entire Fashionistar homepage layout.

    Architecture — asyncio.gather() with 5 concurrent DB queries:
      1. Collections carousel   → catalog app  (CatalogSelector.aget_homepage_collections)
      2. Categories grid        → catalog app  (CatalogSelector.aget_homepage_categories)
      3. Featured products grid → product app  (aget_homepage_products)
      4. Hot deals section      → product app  (aget_homepage_hot_deals)
      5. Public reviews         → product app  (aget_homepage_reviews)

    All 5 queries fire simultaneously on separate PgBouncer connections.
    Total latency = max(single query RTT) ≈ 8–12ms under normal load.

    Cache: ``catalog:homepage:bundle`` — 5 min TTL.
    Cache miss falls back to DB gather transparently (no error surfaced).

    Returns:
        {
            "collections":      list[CollectionCard],   // up to 10
            "categories":       list[CategoryCard],     // up to 10
            "featured_products": list[ProductCard],     // up to 10
            "hot_deals":        list[ProductCard],      // up to 10
            "reviews":          list[ReviewCard],       // up to 8
            "meta": {
                "collections_count": int,
                "categories_count":  int,
                "products_count":    int,
                "hot_deals_count":   int,
                "reviews_count":     int,
            }
        }
    """
    cache_key = (
        f"catalog:homepage:bundle"
        f":{collections_limit}:{categories_limit}"
        f":{products_limit}:{hot_deals_limit}:{reviews_limit}"
    )
    cached = api_cache_get(cache_key)
    if cached is not None:
        return cached

    # ── Cross-app import (guarded — prevents circular import on cold-start) ──
    from apps.product.selectors import (
        aget_homepage_products,
        aget_homepage_hot_deals,
        aget_homepage_reviews,
    )

    # ─────────────────────────────────────────────────────────────────────
    # THE GATHER — 5 independent DB queries executed concurrently.
    # DO NOT await them sequentially; all must launch before any is awaited.
    # ─────────────────────────────────────────────────────────────────────
    (
        raw_collections,
        raw_categories,
        featured_products,
        hot_deals,
        reviews,
    ) = await asyncio.gather(
        CatalogSelector.aget_homepage_collections(limit=collections_limit),
        CatalogSelector.aget_homepage_categories(limit=categories_limit),
        aget_homepage_products(limit=products_limit),
        aget_homepage_hot_deals(limit=hot_deals_limit),
        aget_homepage_reviews(limit=reviews_limit),
    )

    # ── Serialize ─────────────────────────────────────────────────────────
    collections_out = [_homepage_collection_from_dict(row) for row in raw_collections]
    categories_out  = [_homepage_category_from_dict(row) for row in raw_categories]
    products_out    = [_homepage_product_out(p) for p in featured_products]
    hot_deals_out   = [_homepage_product_out(p) for p in hot_deals]
    # reviews already come back as list[dict] from the selector — no extra step

    result = {
        "collections": collections_out,
        "categories": categories_out,
        "featured_products": products_out,
        "hot_deals": hot_deals_out,
        "reviews": reviews,
        "meta": {
            "collections_count": len(collections_out),
            "categories_count": len(categories_out),
            "products_count": len(products_out),
            "hot_deals_count": len(hot_deals_out),
            "reviews_count": len(reviews),
        },
    }

    api_cache_set(cache_key, result, ttl=_TTL_HOMEPAGE)
    return result

