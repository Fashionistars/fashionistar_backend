"""
apps/catalog/utils/__init__.py

Catalog utility helpers — cache key generation, slug helpers, read-time estimation.
All helpers are pure functions with no I/O dependencies.
"""
from __future__ import annotations


# ── Cache key helpers ──────────────────────────────────────────────────────────

def get_catalog_cache_key(entity: str, page: int = 1, page_size: int = 12) -> str:
    """
    Build a canonical Redis cache key for a paginated catalog list endpoint.

    Examples:
        get_catalog_cache_key("categories")         → "catalog:categories:p1:s12"
        get_catalog_cache_key("brands", 2, 24)      → "catalog:brands:p2:s24"
        get_catalog_cache_key("collections", 1, 10) → "catalog:collections:p1:s10"

    Args:
        entity:    Catalog entity name (categories, brands, collections, blog, tags).
        page:      1-indexed page number.
        page_size: Number of items per page.

    Returns:
        str: Dot-separated Redis key.
    """
    return f"catalog:{entity}:p{page}:s{page_size}"


def get_homepage_bundle_key() -> str:
    """
    Return the Redis cache key for the homepage asyncio.gather() bundle.

    This key is set on every GET /api/v1/ninja/catalog/homepage/ response
    and invalidated by the invalidate_catalog_cache Celery task.

    Returns:
        str: "catalog:homepage:bundle"
    """
    return "catalog:homepage:bundle"


def get_category_detail_key(slug: str) -> str:
    """Cache key for a single category detail + sub-categories."""
    return f"catalog:category:detail:{slug}"


def get_brand_detail_key(slug: str) -> str:
    """Cache key for a single brand detail."""
    return f"catalog:brand:detail:{slug}"


def get_collection_detail_key(slug: str) -> str:
    """Cache key for a single collection detail."""
    return f"catalog:collection:detail:{slug}"


def get_catalog_search_key(q: str, page: int = 1, page_size: int = 12) -> str:
    """Cache key for catalog full-text search results."""
    safe_q = q.strip().lower().replace(" ", "_")[:60]
    return f"catalog:search:{safe_q}:p{page}:s{page_size}"


# ── Read-time estimation ───────────────────────────────────────────────────────

def estimate_read_time(text: str, words_per_minute: int = 200) -> int:
    """
    Estimate reading time in minutes from text content.

    Algorithm: word_count ÷ words_per_minute, minimum 1 minute.

    Args:
        text:             Raw text (HTML, markdown, or plain text).
        words_per_minute: Average adult reading speed (default: 200 wpm).

    Returns:
        int: Estimated minutes to read (minimum 1).

    Example:
        estimate_read_time("The quick brown fox " * 200)  → 2
    """
    if not text or not text.strip():
        return 1
    word_count = len(text.split())
    return max(1, round(word_count / words_per_minute))


# ── Slug helpers ───────────────────────────────────────────────────────────────

def build_catalog_slug(name: str, uid_suffix: str | None = None) -> str:
    """
    Generate a URL-safe slug for a catalog entity.

    Args:
        name:       Human-readable name to slugify.
        uid_suffix: Optional short UID appended for uniqueness (e.g. shortuuid[:4]).

    Returns:
        str: Slugified string, e.g. "womens-fashion-ab3c".
    """
    from django.utils.text import slugify as django_slugify

    base = django_slugify(name)[:80]
    if uid_suffix:
        return f"{base}-{uid_suffix}"
    return base