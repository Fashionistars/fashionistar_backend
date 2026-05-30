# apps/catalog/signals.py
"""
Catalog domain Django signals.

Architecture mandate:
    Signals here are ONLY used to bridge Django's ORM post_save/post_delete hooks
    into the EventBus. NO business logic lives here — that belongs in services.

    Pattern:
        post_save / post_delete
            → transaction.on_commit()
                → event_bus.emit(event_name, **payload)
                    → EventBus handler → Celery task (.apply_async())

    Why transaction.on_commit()?
        Guarantees the handler fires only after the DB write is committed.
        Prevents race conditions where a Celery worker reads stale data.

    Currently wired in CatalogConfig.ready() for all 7 catalog models:
        Category, Brand, Collections, CatalogBanner, Tag, CatalogAd, BlogPost
"""
from __future__ import annotations

import logging

from django.db import transaction

logger = logging.getLogger(__name__)


# ── Low-level cache bust (kept for emergency/admin direct use) ─────────────────


def invalidate_catalog_cache(sender, instance, **kwargs) -> None:
    """
    Bust the ``catalog:*`` Redis key namespace via transaction.on_commit().

    Wired on post_save + post_delete for all catalog models in CatalogConfig.ready().
    Delegates to the Celery task so the request thread is never blocked.

    Falls back silently if Celery or Redis is unavailable.
    """

    def _bust() -> None:
        try:
            from apps.catalog.task import (
                invalidate_catalog_cache as _cache_task,
            )

            _cache_task.apply_async()
        except Exception as exc:
            # NEVER abort a DB write because of a cache/queue error.
            logger.debug(
                "catalog cache bust skipped (Redis/Celery unavailable): "
                "model=%s pk=%s exc=%s",
                sender.__name__,
                getattr(instance, "pk", "?"),
                exc,
            )

    transaction.on_commit(_bust)


# ── EventBus bridge handlers ───────────────────────────────────────────────────


def on_category_post_save(sender, instance, created: bool, **kwargs) -> None:
    """Bridge Category post_save → EventBus event."""
    from apps.catalog.events import (
        CATALOG_CATEGORY_CREATED,
        CATALOG_CATEGORY_UPDATED,
    )
    from apps.common.events import event_bus

    event_name = CATALOG_CATEGORY_CREATED if created else CATALOG_CATEGORY_UPDATED

    def _emit():
        event_bus.emit(event_name, category_id=str(instance.pk))

    transaction.on_commit(_emit)


def on_category_post_delete(sender, instance, **kwargs) -> None:
    """Bridge Category post_delete → EventBus event."""
    from apps.catalog.events import CATALOG_CATEGORY_DELETED
    from apps.common.events import event_bus

    def _emit():
        event_bus.emit(CATALOG_CATEGORY_DELETED, category_id=str(instance.pk))

    transaction.on_commit(_emit)


def on_brand_post_save(sender, instance, created: bool, **kwargs) -> None:
    """Bridge Brand post_save → EventBus event."""
    from apps.catalog.events import CATALOG_BRAND_CREATED, CATALOG_BRAND_UPDATED
    from apps.common.events import event_bus

    event_name = CATALOG_BRAND_CREATED if created else CATALOG_BRAND_UPDATED

    def _emit():
        event_bus.emit(event_name, brand_id=str(instance.pk))

    transaction.on_commit(_emit)


def on_collection_post_save(sender, instance, created: bool, **kwargs) -> None:
    """Bridge Collections post_save → EventBus event."""
    from apps.catalog.events import (
        CATALOG_COLLECTION_CREATED,
        CATALOG_COLLECTION_PUBLISHED,
        CATALOG_COLLECTION_UNPUBLISHED,
    )
    from apps.common.events import event_bus

    if created:
        event_name = CATALOG_COLLECTION_CREATED
    else:
        # Treat any save of a soft-deleted collection as unpublished
        event_name = (
            CATALOG_COLLECTION_UNPUBLISHED
            if getattr(instance, "deleted_at", None)
            else CATALOG_COLLECTION_PUBLISHED
        )

    def _emit():
        event_bus.emit(event_name, collection_id=str(instance.pk))

    transaction.on_commit(_emit)


def on_banner_post_save(sender, instance, **kwargs) -> None:
    """Bridge CatalogBanner post_save → EventBus event."""
    from apps.catalog.events import (
        CATALOG_BANNER_ACTIVATED,
        CATALOG_BANNER_EXPIRED,
    )
    from apps.common.events import event_bus

    event_name = CATALOG_BANNER_ACTIVATED if instance.is_active else CATALOG_BANNER_EXPIRED

    def _emit():
        event_bus.emit(event_name, banner_id=str(instance.pk))

    transaction.on_commit(_emit)


def on_banner_post_delete(sender, instance, **kwargs) -> None:
    """Bridge CatalogBanner post_delete → EventBus event."""
    from apps.catalog.events import CATALOG_BANNER_DELETED
    from apps.common.events import event_bus

    def _emit():
        event_bus.emit(CATALOG_BANNER_DELETED, banner_id=str(instance.pk))

    transaction.on_commit(_emit)


def on_blog_post_save(sender, instance, **kwargs) -> None:
    """Bridge BlogPost post_save → EventBus + cache bust."""
    from apps.catalog.events import (
        CATALOG_BLOG_PUBLISHED,
        CATALOG_BLOG_UNPUBLISHED,
    )
    from apps.common.events import event_bus

    from .models.blog import BlogPostStatus

    event_name = (
        CATALOG_BLOG_PUBLISHED
        if instance.status == BlogPostStatus.PUBLISHED
        else CATALOG_BLOG_UNPUBLISHED
    )

    def _emit():
        event_bus.emit(event_name, post_id=str(instance.pk))

    transaction.on_commit(_emit)
