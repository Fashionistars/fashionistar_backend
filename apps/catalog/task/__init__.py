"""
apps/catalog/task/__init__.py

Catalog Celery background tasks.

All tasks are triggered via transaction.on_commit() in signals.py to guarantee
they only run after the triggering DB write has been durably committed.

Naming convention: catalog.<action>
"""
from __future__ import annotations

import logging

from celery import shared_task  # type: ignore[import]

logger = logging.getLogger(__name__)


# ── Cache Invalidation ──────────────────────────────────────────────────────


@shared_task(
    name="catalog.invalidate_cache",
    bind=True,
    max_retries=3,
    default_retry_delay=5,
    ignore_result=True,
)
def invalidate_catalog_cache(self) -> str:  # type: ignore[override]
    """
    Invalidate the entire ``catalog:*`` Redis key namespace.

    Called by signals.py via transaction.on_commit() after any catalog
    model write (Category, Brand, Collections, CatalogBanner, Tag,
    CatalogAd, BlogPost).

    Falls back silently if Redis is unavailable (dev/test environments).
    """
    try:
        from apps.common.utils.redis import api_cache_delete_pattern

        deleted = api_cache_delete_pattern("catalog:*")
        msg = f"catalog cache busted: keys_deleted={deleted}"
        logger.info(msg)
        return msg
    except Exception as exc:
        logger.warning("catalog cache bust failed (non-fatal): %s", exc)
        try:
            raise self.retry(exc=exc)
        except self.MaxRetriesExceededError:
            logger.error("catalog cache bust max retries exceeded: %s", exc)
            return f"cache bust failed after retries: {exc}"


# ── Per-Entity Product Count Refreshers ────────────────────────────────────


@shared_task(
    name="catalog.update_category_product_count",
    bind=True,
    max_retries=3,
    default_retry_delay=10,
    ignore_result=True,
)
def update_category_product_count(self, category_id: str | int) -> str:  # type: ignore[override]
    """
    Recalculate and persist cached_product_count for a single Category.

    Args:
        category_id: PK of the Category to refresh.
    """
    try:
        from apps.catalog.models import Category

        live_count = Category.objects.get(pk=category_id).category_products.count()
        Category.objects.filter(pk=category_id).update(cached_product_count=live_count)
        msg = f"category {category_id} cached_product_count={live_count}"
        logger.debug(msg)
        return msg
    except Exception as exc:  # Category.DoesNotExist or DB error
        logger.exception("update_category_product_count failed for pk=%s: %s", category_id, exc)
        raise self.retry(exc=exc)


@shared_task(
    name="catalog.update_brand_product_count",
    bind=True,
    max_retries=3,
    default_retry_delay=10,
    ignore_result=True,
)
def update_brand_product_count(self, brand_id: str | int) -> str:  # type: ignore[override]
    """
    Recalculate and persist cached_product_count for a single Brand.

    Args:
        brand_id: PK of the Brand to refresh.
    """
    try:
        from apps.catalog.models import Brand

        brand = Brand.objects.get(pk=brand_id)
        # brand_products is the related_name from Product.brand FK
        live_count = (
            brand.brand_products.count()
            if hasattr(brand, "brand_products")
            else 0
        )
        Brand.objects.filter(pk=brand_id).update(cached_product_count=live_count)
        msg = f"brand {brand_id} cached_product_count={live_count}"
        logger.debug(msg)
        return msg
    except Exception as exc:
        logger.exception("update_brand_product_count failed for pk=%s: %s", brand_id, exc)
        raise self.retry(exc=exc)


@shared_task(
    name="catalog.update_collection_product_count",
    bind=True,
    max_retries=3,
    default_retry_delay=10,
    ignore_result=True,
)
def update_collection_product_count(self, collection_id: str | int) -> str:  # type: ignore[override]
    """
    Recalculate and persist cached_product_count for a Collections instance.

    Args:
        collection_id: PK of the Collections model to refresh.
    """
    try:
        from apps.catalog.models import Collections

        coll = Collections.objects.get(pk=collection_id)
        # vendor_collections is the related_name from VendorCollection.collection FK
        live_count = (
            coll.vendor_collections.count()
            if hasattr(coll, "vendor_collections")
            else 0
        )
        Collections.objects.filter(pk=collection_id).update(cached_product_count=live_count)
        msg = f"collection {collection_id} cached_product_count={live_count}"
        logger.debug(msg)
        return msg
    except Exception as exc:
        logger.exception(
            "update_collection_product_count failed for pk=%s: %s", collection_id, exc
        )
        raise self.retry(exc=exc)
