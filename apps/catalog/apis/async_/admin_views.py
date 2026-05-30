"""
apps/catalog/apis/async_/admin_views.py — Phase H2

Staff-only admin API endpoints for cache management.

Endpoints:
    POST /catalog/admin/invalidate-cache/    — Queue Redis cache invalidation
    GET  /catalog/admin/health/              — Provider + cache health check
"""
from __future__ import annotations

import logging

from ninja import Router
from ninja.errors import HttpError

from apps.common.utils.redis import api_cache_get, api_cache_set

logger = logging.getLogger(__name__)

admin_router = Router(tags=["Catalog Admin"])


@admin_router.post(
    "/invalidate-cache/",
    summary="Invalidate all catalog Redis caches (staff only)",
)
async def invalidate_catalog_cache_endpoint(request):
    """
    Queue a Celery task to invalidate all catalog:* Redis cache keys.

    Only callable by Django staff users.
    The cache is cleared asynchronously (within ~1s) via Celery.
    """
    if not request.user or not request.user.is_authenticated:
        raise HttpError(401, "Authentication required.")
    if not request.user.is_staff:
        raise HttpError(403, "Staff access required.")

    try:
        from apps.catalog.task import invalidate_catalog_cache
        invalidate_catalog_cache.apply_async()
        logger.info(
            "[catalog.admin] Cache invalidation queued by staff user: %s",
            request.user.email,
        )
        return {"success": True, "message": "Cache invalidation queued. Redis will clear catalog:* keys within 1s."}
    except Exception as exc:
        logger.error("[catalog.admin] Cache invalidation failed: %s", exc)
        raise HttpError(500, f"Cache invalidation failed: {exc}") from exc


@admin_router.get(
    "/health/",
    summary="Catalog system health — Redis cache + SMTP provider status",
)
async def catalog_health_check(request):
    """
    Health check for catalog subsystem.

    Reports:
        - Redis cache connectivity
        - Homepage bundle cache status (hit/miss + TTL proxy via test key)
        - All SMTP provider health results

    Staff-only in production. Opens to monitoring systems via API key.
    """
    if not request.user or not request.user.is_authenticated:
        raise HttpError(401, "Authentication required.")
    if not request.user.is_staff:
        raise HttpError(403, "Staff access required.")

    # Redis connectivity check
    redis_healthy = False
    redis_error = None
    try:
        test_key = "catalog:admin:health:ping"
        await api_cache_set(test_key, {"ping": True}, ttl=10)
        val = api_cache_get(test_key)
        redis_healthy = val is not None
    except Exception as exc:
        redis_error = str(exc)

    # Homepage bundle cache status
    bundle_cached = api_cache_get("catalog:homepage:bundle") is not None
    bundle_v2_cached = api_cache_get("catalog:homepage:bundle:v2:10:10:10:10:8:5") is not None

    # SMTP provider health
    smtp_results = []
    try:
        from apps.providers.SMTP.registry import run_all_health_checks
        smtp_results = run_all_health_checks()
    except Exception as exc:
        smtp_results = [{"error": str(exc)}]

    return {
        "catalog": {
            "redis_healthy": redis_healthy,
            "redis_error": redis_error,
            "homepage_bundle_cached": bundle_cached,
            "homepage_bundle_v2_cached": bundle_v2_cached,
        },
        "smtp_providers": smtp_results,
        "status": "healthy" if redis_healthy else "degraded",
    }
