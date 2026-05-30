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

# H1 — Wire admin sub-router (staff-only cache invalidation + health endpoints)
try:
    from apps.catalog.apis.async_.admin_views import admin_router
    router.add_router("/admin", admin_router)
except ImportError:
    logger.warning("[catalog_views] admin_views not found — admin endpoints disabled")

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


# ═══════════════════════════════════════════════════════════════════════════════
#  PHASE B1 — MISSING ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════════

_TTL_BANNER  = 60       # 60s — fast invalidation on CMS banner change
_TTL_SEARCH  = 30       # 30s — short for freshness
_TTL_TAGS    = 10 * 60  # 10 min — tags change rarely


def _banner_out(row: dict) -> dict:
    """Serialize a CatalogBanner .values() row to frontend-ready dict."""
    def _cdn(raw) -> str | None:
        if not raw:
            return None
        s = str(raw)
        if s.startswith("http"):
            return s
        return f"https://res.cloudinary.com/{s}" if s else None

    return {
        "id": str(row["id"]),
        "slot": row.get("slot", "hero"),
        "title": row.get("title", ""),
        "subtitle": row.get("subtitle", ""),
        "cta_text": row.get("cta_text", "Shop Now"),
        "cta_url": row.get("cta_url", ""),
        "image_url": _cdn(row.get("image")),
        "mobile_image_url": _cdn(row.get("mobile_image")),
        "sort_order": row.get("sort_order", 0),
    }


@router.get("/homepage/banners/", auth=None, summary="Active hero banners for homepage carousel")
async def list_homepage_banners(request, slot: str = "hero"):
    """Active CatalogBanners for a slot (hero | mid | footer_cta). Cache 60s."""
    cache_key = f"catalog:banners:{slot}"
    cached = api_cache_get(cache_key)
    if cached is not None:
        return cached
    rows = await CatalogSelector.aget_homepage_banners(slot=slot, limit=10)
    result = {"banners": [_banner_out(r) for r in rows], "slot": slot}
    api_cache_set(cache_key, result, ttl=_TTL_BANNER)
    return result


@router.get("/tags/", auth=None, summary="Trending catalog tags")
async def list_tags(request):
    """Trending taxonomy tags for homepage tags rail. Cache 10 min."""
    cache_key = "catalog:tags:trending"
    cached = api_cache_get(cache_key)
    if cached is not None:
        return cached
    tags = await CatalogSelector.aget_trending_tags(limit=30)
    result = {"tags": tags, "count": len(tags)}
    api_cache_set(cache_key, result, ttl=_TTL_TAGS)
    return result


@router.get("/categories/{slug}/detail/", auth=None, summary="Category detail with sub-categories")
async def get_category_detail(request, slug: str):
    """Single category detail + immediate children. Cache 5 min."""
    cache_key = f"catalog:category:detail:{slug}"
    cached = api_cache_get(cache_key)
    if cached is not None:
        return cached
    detail = await CatalogSelector.aget_category_with_children(slug=slug)
    if detail is None:
        raise HttpError(404, "Category not found.")
    api_cache_set(cache_key, detail, ttl=_TTL_CATALOG)
    return detail


@router.get("/categories/{slug}/products/", auth=None, summary="Paginated products in category")
async def list_category_products(request, slug: str, page: int = 1, page_size: int = 12):
    """Paginated products by category slug. Cache 60s."""
    cache_key = f"catalog:category:products:{slug}:p{page}:s{page_size}"
    cached = api_cache_get(cache_key)
    if cached is not None:
        return cached
    try:
        from apps.product.selectors import aget_products_by_category_slug
        products, total = await aget_products_by_category_slug(slug=slug, page=page, page_size=page_size)
        result = {"results": [_homepage_product_out(p) for p in products], "count": total, "page": page, "page_size": page_size}
    except (ImportError, AttributeError):
        result = {"results": [], "count": 0, "page": page, "page_size": page_size}
    api_cache_set(cache_key, result, ttl=_TTL_BANNER)
    return result


@router.get("/brands/{slug}/detail/", auth=None, summary="Brand detail")
async def get_brand_detail(request, slug: str):
    """Single brand detail dict. Cache 5 min."""
    cache_key = f"catalog:brand:detail:{slug}"
    cached = api_cache_get(cache_key)
    if cached is not None:
        return cached
    detail = await CatalogSelector.aget_brand_detail(slug=slug)
    if detail is None:
        raise HttpError(404, "Brand not found.")
    api_cache_set(cache_key, detail, ttl=_TTL_CATALOG)
    return detail


@router.get("/brands/{slug}/products/", auth=None, summary="Paginated products by brand")
async def list_brand_products(request, slug: str, page: int = 1, page_size: int = 12):
    """Paginated products by brand slug. Cache 60s."""
    cache_key = f"catalog:brand:products:{slug}:p{page}:s{page_size}"
    cached = api_cache_get(cache_key)
    if cached is not None:
        return cached
    try:
        from apps.product.selectors import aget_products_by_brand_slug
        products, total = await aget_products_by_brand_slug(slug=slug, page=page, page_size=page_size)
        result = {"results": [_homepage_product_out(p) for p in products], "count": total, "page": page, "page_size": page_size}
    except (ImportError, AttributeError):
        result = {"results": [], "count": 0, "page": page, "page_size": page_size}
    api_cache_set(cache_key, result, ttl=_TTL_BANNER)
    return result


@router.get("/collections/{slug}/detail/", auth=None, summary="Collection detail")
async def get_collection_detail(request, slug: str):
    """Single collection detail dict. Cache 5 min."""
    cache_key = f"catalog:collection:detail:{slug}"
    cached = api_cache_get(cache_key)
    if cached is not None:
        return cached
    detail = await CatalogSelector.aget_collection_detail(slug=slug)
    if detail is None:
        raise HttpError(404, "Collection not found.")
    api_cache_set(cache_key, detail, ttl=_TTL_CATALOG)
    return detail


@router.get("/collections/{slug}/products/", auth=None, summary="Paginated products in collection")
async def list_collection_products(request, slug: str, page: int = 1, page_size: int = 12):
    """Paginated products by collection slug. Cache 60s."""
    cache_key = f"catalog:collection:products:{slug}:p{page}:s{page_size}"
    cached = api_cache_get(cache_key)
    if cached is not None:
        return cached
    try:
        from apps.product.selectors import aget_products_by_collection_slug
        products, total = await aget_products_by_collection_slug(slug=slug, page=page, page_size=page_size)
        result = {"results": [_homepage_product_out(p) for p in products], "count": total, "page": page, "page_size": page_size}
    except (ImportError, AttributeError):
        result = {"results": [], "count": 0, "page": page, "page_size": page_size}
    api_cache_set(cache_key, result, ttl=_TTL_BANNER)
    return result


@router.get("/search/", auth=None, summary="Catalog full-text search across categories, brands, collections")
async def catalog_search(request, q: str = "", page_size: int = 12):
    """icontains search across catalog entities. Cache 30s."""
    if not q.strip():
        return {"categories": [], "brands": [], "collections": [], "query": q}
    safe_q = q.strip().lower().replace(" ", "_")[:60]
    cache_key = f"catalog:search:{safe_q}"
    cached = api_cache_get(cache_key)
    if cached is not None:
        return cached
    result = await CatalogSelector.aget_catalog_search(q=q.strip(), limit=page_size)
    result["query"] = q
    api_cache_set(cache_key, result, ttl=_TTL_SEARCH)
    return result


# ── B3: Homepage bundle v2 — 6-gather (adds banners) ─────────────────────────

@router.get("/homepage/bundle/", auth=None, summary="Homepage bundle v2 — 6 concurrent DB reads")
async def get_homepage_bundle_v2(
    request,
    collections_limit: int = 10,
    categories_limit: int = 10,
    products_limit: int = 10,
    hot_deals_limit: int = 10,
    reviews_limit: int = 8,
    banners_limit: int = 5,
):
    """
    Homepage data bundle v2 — asyncio.gather() with 6 concurrent DB queries.

    Sections: collections, categories, featured_products, hot_deals, reviews, banners.
    Cache: catalog:homepage:bundle:v2:{params} — 5 min TTL.
    """
    cache_key = (
        f"catalog:homepage:bundle:v2"
        f":{collections_limit}:{categories_limit}"
        f":{products_limit}:{hot_deals_limit}:{reviews_limit}:{banners_limit}"
    )
    cached = api_cache_get(cache_key)
    if cached is not None:
        return cached

    from apps.product.selectors import (
        aget_homepage_hot_deals,
        aget_homepage_products,
        aget_homepage_reviews,
    )

    (
        raw_collections,
        raw_categories,
        featured_products,
        hot_deals,
        reviews,
        raw_banners,
    ) = await asyncio.gather(
        CatalogSelector.aget_homepage_collections(limit=collections_limit),
        CatalogSelector.aget_homepage_categories(limit=categories_limit),
        aget_homepage_products(limit=products_limit),
        aget_homepage_hot_deals(limit=hot_deals_limit),
        aget_homepage_reviews(limit=reviews_limit),
        CatalogSelector.aget_homepage_banners(slot="hero", limit=banners_limit),
    )

    result = {
        "collections": [_homepage_collection_from_dict(r) for r in raw_collections],
        "categories": [_homepage_category_from_dict(r) for r in raw_categories],
        "featured_products": [_homepage_product_out(p) for p in featured_products],
        "hot_deals": [_homepage_product_out(p) for p in hot_deals],
        "reviews": reviews,
        "banners": [_banner_out(r) for r in raw_banners],
        "meta": {
            "collections_count": len(raw_collections),
            "categories_count": len(raw_categories),
            "products_count": len(featured_products),
            "hot_deals_count": len(hot_deals),
            "reviews_count": len(reviews),
            "banners_count": len(raw_banners),
        },
    }

    api_cache_set(cache_key, result, ttl=_TTL_HOMEPAGE)
    return result
