"""Catalog Django-Ninja async read router — with Redis API caching.

Cache Strategy (Section 4 of apps/common/utils/redis.py):
  - api_cache_get / api_cache_set use Django's cache framework (django-redis backend).
  - IGNORE_EXCEPTIONS=True ensures cache outages degrade to DB fallback silently.
  - No retry loop — cache miss is instant, never blocks the response.
  - TTLs are intentionally short for mutable catalog data:
      categories / brands  → 5 min  (admin edits are infrequent)
      collections          → 5 min  (merchandising surfaces)
      blog posts           → 10 min (editorial content, lower mutation rate)
  - Cache keys include page + page_size for correct per-page caching.
  - Write mutations (admin panel) MUST call api_cache_delete_pattern("catalog:*")
    to invalidate stale entries — currently handled via Django admin post-save signal.
"""

from __future__ import annotations

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

router = Router(tags=["Catalog — Async Reads"])

# ── TTLs ────────────────────────────────────────────────────────────────────────
_TTL_CATALOG = 5 * 60    # 5 minutes — categories, brands, collections
_TTL_BLOG    = 10 * 60   # 10 minutes — editorial content


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
