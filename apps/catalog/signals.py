# apps/catalog/signals.py
"""
Catalog domain Django signals.

Currently wired in CatalogConfig.ready():
  - post_save  → invalidate_catalog_cache  (all 5 catalog models)
  - post_delete → invalidate_catalog_cache  (all 5 catalog models)

Design:
  All handlers are fail-safe — a Redis outage MUST NOT abort a Django admin
  save() operation or any service-layer write.  Every Redis interaction is
  wrapped in try/except with a debug log on failure.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def invalidate_catalog_cache(sender, instance, **kwargs) -> None:
    """
    Invalidate the entire ``catalog:*`` Redis key namespace after any write.

    Called on:
        - post_save  (create and update)
        - post_delete

    Clears all paginated list-endpoint caches for:
        catalog:categories:{page}:{page_size}
        catalog:brands:{page}:{page_size}
        catalog:collections:{page}:{page_size}
        catalog:blog:{page}:{page_size}

    Falls back silently if Redis is unavailable.
    """
    try:
        from apps.common.utils.redis import api_cache_delete_pattern

        deleted = api_cache_delete_pattern("catalog:*")
        logger.debug(
            "catalog cache busted: model=%s pk=%s keys_deleted=%s",
            sender.__name__,
            getattr(instance, "pk", "?"),
            deleted,
        )
    except Exception as exc:
        # Never abort a DB write because of a cache error.
        logger.debug(
            "catalog cache bust skipped (Redis unavailable): model=%s exc=%s",
            sender.__name__,
            exc,
        )
