"""
apps/catalog/events/__init__.py

Catalog EventBus event names and subscription helpers.

Architecture rule:
    NO Django signals for business logic flows.
    All catalog domain events flow through EventBus.
    Heavy work (email, reports) is dispatched to Celery inside handlers.

Event naming convention: catalog.<entity>.<action>

Usage:
    # Emit after a category is updated in a service:
    from apps.catalog.events import CATALOG_CATEGORY_UPDATED
    from apps.common.events import event_bus
    event_bus.emit_on_commit(CATALOG_CATEGORY_UPDATED, category_id=str(instance.pk))

    # Subscribe in an app's ready() hook:
    from apps.catalog.events import subscribe_catalog_events
    subscribe_catalog_events()
"""
from __future__ import annotations

import logging

from apps.common.events import event_bus

logger = logging.getLogger(__name__)

# ── Event Name Constants ───────────────────────────────────────────────────────

# Category lifecycle
CATALOG_CATEGORY_CREATED = "catalog.category.created"
CATALOG_CATEGORY_UPDATED = "catalog.category.updated"
CATALOG_CATEGORY_DELETED = "catalog.category.deleted"

# Collection lifecycle
CATALOG_COLLECTION_CREATED = "catalog.collection.created"
CATALOG_COLLECTION_PUBLISHED = "catalog.collection.published"
CATALOG_COLLECTION_UNPUBLISHED = "catalog.collection.unpublished"
CATALOG_COLLECTION_DELETED = "catalog.collection.deleted"

# Banner lifecycle
CATALOG_BANNER_ACTIVATED = "catalog.banner.activated"
CATALOG_BANNER_EXPIRED = "catalog.banner.expired"
CATALOG_BANNER_DELETED = "catalog.banner.deleted"

# Brand lifecycle
CATALOG_BRAND_CREATED = "catalog.brand.created"
CATALOG_BRAND_UPDATED = "catalog.brand.updated"

# Blog lifecycle
CATALOG_BLOG_PUBLISHED = "catalog.blog.published"
CATALOG_BLOG_UNPUBLISHED = "catalog.blog.unpublished"

# Tag lifecycle
CATALOG_TAG_CREATED = "catalog.tag.created"
CATALOG_TAG_TRENDING_UPDATED = "catalog.tag.trending_updated"

# 2026 — Style Guide lifecycle
CATALOG_STYLE_GUIDE_CREATED = "catalog.style_guide.created"
CATALOG_STYLE_GUIDE_PUBLISHED = "catalog.style_guide.published"
CATALOG_STYLE_GUIDE_UNPUBLISHED = "catalog.style_guide.unpublished"

# 2026 — Lookbook lifecycle
CATALOG_LOOKBOOK_PUBLISHED = "catalog.lookbook.published"
CATALOG_LOOKBOOK_UNPUBLISHED = "catalog.lookbook.unpublished"

# 2026 — Trending
CATALOG_TRENDING_REFRESHED = "catalog.trending.refreshed"
CATALOG_FASHION_TREND_CREATED = "catalog.fashion_trend.created"
CATALOG_FASHION_TREND_UPDATED = "catalog.fashion_trend.updated"


# ── Default Event Handlers ─────────────────────────────────────────────────────


def _on_category_updated(category_id: str, **kwargs) -> None:
    """On category save → queue cache invalidation + counter refresh."""
    try:
        from apps.catalog.task import (
            invalidate_catalog_cache,
            update_category_product_count,
        )

        invalidate_catalog_cache.apply_async()
        if category_id:
            update_category_product_count.apply_async(args=[int(category_id)])
    except Exception as exc:
        logger.warning("_on_category_updated handler failed (non-fatal): %s", exc)


def _on_collection_published(collection_id: str, **kwargs) -> None:
    """On collection publish → invalidate catalog cache."""
    try:
        from apps.catalog.task import invalidate_catalog_cache

        invalidate_catalog_cache.apply_async()
        logger.debug("catalog cache invalidated after collection published: %s", collection_id)
    except Exception as exc:
        logger.warning("_on_collection_published handler failed (non-fatal): %s", exc)


def _on_banner_change(**kwargs) -> None:
    """On banner activated/expired → bust the homepage bundle cache."""
    try:
        from apps.catalog.task import invalidate_catalog_cache

        invalidate_catalog_cache.apply_async()
        logger.debug("catalog cache invalidated after banner change")
    except Exception as exc:
        logger.warning("_on_banner_change handler failed (non-fatal): %s", exc)


def _on_brand_updated(brand_id: str, **kwargs) -> None:
    """On brand save → queue cache invalidation + counter refresh."""
    try:
        from apps.catalog.task import invalidate_catalog_cache, update_brand_product_count

        invalidate_catalog_cache.apply_async()
        if brand_id:
            update_brand_product_count.apply_async(args=[int(brand_id)])
    except Exception as exc:
        logger.warning("_on_brand_updated handler failed (non-fatal): %s", exc)


# ── Subscription Bootstrapper ──────────────────────────────────────────────────


def subscribe_catalog_events() -> None:
    """
    Wire all catalog default event handlers to the event bus.

    Called once from CatalogConfig.ready() — idempotent (EventBus deduplicates).
    """
    # Category
    event_bus.subscribe(CATALOG_CATEGORY_CREATED, _on_category_updated)
    event_bus.subscribe(CATALOG_CATEGORY_UPDATED, _on_category_updated)
    event_bus.subscribe(CATALOG_CATEGORY_DELETED, _on_category_updated)

    # Collection
    event_bus.subscribe(CATALOG_COLLECTION_PUBLISHED, _on_collection_published)
    event_bus.subscribe(CATALOG_COLLECTION_UNPUBLISHED, _on_collection_published)
    event_bus.subscribe(CATALOG_COLLECTION_DELETED, _on_collection_published)

    # Banner
    event_bus.subscribe(CATALOG_BANNER_ACTIVATED, _on_banner_change)
    event_bus.subscribe(CATALOG_BANNER_EXPIRED, _on_banner_change)
    event_bus.subscribe(CATALOG_BANNER_DELETED, _on_banner_change)

    # Brand
    event_bus.subscribe(CATALOG_BRAND_CREATED, _on_brand_updated)
    event_bus.subscribe(CATALOG_BRAND_UPDATED, _on_brand_updated)

    logger.info("Catalog EventBus subscriptions registered.")
