# apps/common/utils/redis.py
"""
Enterprise Redis Utility Layer for Fashionistar.

All Redis interactions (connection pooling, retry logic, presign caching,
session data, OTP storage) are centralized here.

Design Principles
─────────────────
- Fail-safe: ALL Redis operations degrade gracefully to None / False on
  connection errors — the caller decides whether to fall back or error out.
- Connection pooling: uses ``django_redis.get_redis_connection("default")``
  which shares the same pool configured in settings.CACHES['default'].
- Retry: up to 3 attempts with 1-second back-off before giving up.
- Serialization: JSON for structured data, plain string for simple scalars.
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any, Optional

from django_redis import get_redis_connection

logger = logging.getLogger(__name__)

# ─── Retry configuration ─────────────────────────────────────────────────────
REDIS_MAX_RETRIES: int = 3
REDIS_RETRY_DELAY: int = 1  # seconds between each retry attempt


# ─────────────────────────────────────────────────────────────────────────────
# 1. Connection
# ─────────────────────────────────────────────────────────────────────────────

def get_redis_connection_safe(
    max_retries: int = REDIS_MAX_RETRIES,
    retry_delay: int = REDIS_RETRY_DELAY,
) -> Optional[Any]:
    """
    Establish a safe Redis connection with exponential-style retry.

    Returns the live ``StrictRedis`` connection object, or ``None`` if Redis
    is unreachable after all retries.  Callers should treat ``None`` as a
    cache-miss and fall back to the authoritative data source.

    Args:
        max_retries:  Number of connection attempts.
        retry_delay:  Seconds to wait between retries.

    Returns:
        ``redis.StrictRedis`` or ``None``.
    """
    for attempt in range(max_retries):
        try:
            conn = get_redis_connection("default")
            conn.ping()
            return conn
        except Exception as exc:
            logger.error(
                "Redis connection error (attempt %d/%d): %s",
                attempt + 1, max_retries, exc,
            )
            if attempt < max_retries - 1:
                time.sleep(retry_delay)

    logger.error("Max Redis connection retries reached. Redis unavailable.")
    return None


# ─────────────────────────────────────────────────────────────────────────────
# 2. Cloudinary Pre-sign Cache
# ─────────────────────────────────────────────────────────────────────────────

# Key template: cloudinary:presign:{user_id}:{asset_type}[:{context_id}]
# context_id is optional — used for bulk/product uploads to avoid cache collisions
_PRESIGN_KEY = "cloudinary:presign:{user_id}:{asset_type}"
_PRESIGN_TTL = 3300  # 55 minutes — slightly less than the 1-hour signature validity


def _presign_cache_key(user_id: str, asset_type: str, context_id: Optional[str] = None) -> str:
    """
    Build the Redis cache key for a presign.

    If ``context_id`` is given (e.g. product UUID, bulk session ID, or a
    timestamp string), it is appended to make each upload context unique.
    This prevents the same cached presign from being returned when a user
    uploads multiple different products in rapid succession.

    Examples:
        Avatar (single, cached):    ``cloudinary:presign:uid123:avatar``
        Product A (unique):         ``cloudinary:presign:uid123:product_image:prod-abc``
        Product B (unique):         ``cloudinary:presign:uid123:product_image:prod-xyz``
        Bulk session:               ``cloudinary:presign:uid123:product_image:bulk-20260319T234500``
    """
    base = _PRESIGN_KEY.format(user_id=user_id, asset_type=asset_type)
    if context_id:
        return f"{base}:{context_id}"
    return base


def cache_upload_presign(
    user_id: str,
    asset_type: str,
    params: dict,
    context_id: Optional[str] = None,
) -> bool:
    """
    Cache a Cloudinary pre-signed upload parameter set in Redis.

    Key format: ``cloudinary:presign:{user_id}:{asset_type}[:{context_id}]``
    TTL:        3300 seconds (55 minutes)

    ``context_id`` is optional.  Pass it when the same user will upload
    multiple items of the same asset_type in quick succession (e.g. bulk
    product images).  This ensures each upload gets a unique signed presign
    rather than getting the same cached one.

    Args:
        user_id:    The UUID string of the requesting user.
        asset_type: One of ``avatar``, ``product_image``, ``product_video``,
                    ``measurement``.
        params:     Dict of presign params.
        context_id: Optional disambiguation key (product UUID, bulk session ID).

    Returns:
        ``True`` on success, ``False`` if Redis is unavailable.
    """
    conn = get_redis_connection_safe()
    if conn is None:
        return False
    try:
        key = _presign_cache_key(user_id, asset_type, context_id)
        conn.setex(key, _PRESIGN_TTL, json.dumps(params))
        logger.debug("Presign cached for user=%s asset=%s context=%s", user_id, asset_type, context_id)
        return True
    except Exception as exc:
        logger.warning("Failed to cache presign for user=%s: %s", user_id, exc)
        return False


def get_cached_presign(
    user_id: str,
    asset_type: str,
    context_id: Optional[str] = None,
) -> Optional[dict]:
    """
    Retrieve cached Cloudinary presign params from Redis.

    Pass the same ``context_id`` used in ``cache_upload_presign`` to hit
    the correct per-context cache entry.

    Returns:
        The cached params dict, or ``None`` on miss / Redis unavailability.
    """
    conn = get_redis_connection_safe()
    if conn is None:
        return None
    try:
        key = _presign_cache_key(user_id, asset_type, context_id)
        raw = conn.get(key)
        if raw:
            logger.debug("Presign cache HIT for user=%s asset=%s context=%s", user_id, asset_type, context_id)
            return json.loads(raw)
        return None
    except Exception as exc:
        logger.warning("Failed to read presign cache for user=%s: %s", user_id, exc)
        return None


def invalidate_upload_presign(
    user_id: str,
    asset_type: str,
    context_id: Optional[str] = None,
) -> bool:
    """
    Invalidate (delete) a cached presign token for the given user + asset type.

    Call this after a successful upload confirmation so the next upload request
    generates a fresh signature rather than reusing the old one.

    Pass ``context_id`` if you used one during caching.
    """
    conn = get_redis_connection_safe()
    if conn is None:
        return False
    try:
        key = _presign_cache_key(user_id, asset_type, context_id)
        conn.delete(key)
        return True
    except Exception as exc:
        logger.warning("Failed to invalidate presign cache for user=%s: %s", user_id, exc)
        return False


# ─────────────────────────────────────────────────────────────────────────────
# 3. Generic OTP / short-lived value cache utilities
# ─────────────────────────────────────────────────────────────────────────────

def redis_set(key: str, value: Any, ttl: int = 300) -> bool:
    """
    Store any JSON-serializable value in Redis with an explicit TTL (seconds).

    Returns ``True`` on success, ``False`` on failure.
    """
    conn = get_redis_connection_safe()
    if conn is None:
        return False
    try:
        conn.setex(key, ttl, json.dumps(value))
        return True
    except Exception as exc:
        logger.warning("redis_set failed for key=%s: %s", key, exc)
        return False


def redis_get(key: str) -> Any:
    """
    Retrieve a JSON-decoded value from Redis.

    Returns the deserialized value, or ``None`` on miss / error.
    """
    conn = get_redis_connection_safe()
    if conn is None:
        return None
    try:
        raw = conn.get(key)
        return json.loads(raw) if raw else None
    except Exception as exc:
        logger.warning("redis_get failed for key=%s: %s", key, exc)
        return None


def redis_delete(key: str) -> bool:
    """Delete a key from Redis. Returns ``True`` on success."""
    conn = get_redis_connection_safe()
    if conn is None:
        return False
    try:
        conn.delete(key)
        return True
    except Exception as exc:
        logger.warning("redis_delete failed for key=%s: %s", key, exc)
        return False


def redis_incr(key: str, ttl: int = 60) -> Optional[int]:
    """
    Atomically increment a Redis counter.  Creates it at 1 if it does not
    exist, and sets the TTL **only on creation** so existing keys keep their
    remaining TTL.

    Useful for rate-limiting and analytics counters.

    Returns the new integer value, or ``None`` on error.
    """
    conn = get_redis_connection_safe()
    if conn is None:
        return None
    try:
        pipe = conn.pipeline()
        pipe.incr(key)
        pipe.expire(key, ttl, nx=True)  # set TTL only if not already set
        results = pipe.execute()
        return results[0]
    except Exception as exc:
        logger.warning("redis_incr failed for key=%s: %s", key, exc)
        return None


# ─────────────────────────────────────────────────────────────────────────────
# 4. API Endpoint Caching  ← SINGLE-TRY (no retry loop for API responses)
# ─────────────────────────────────────────────────────────────────────────────
#
# Design decision (vs OTP / presign caching above)
# ─────────────────────────────────────────────────
# For API endpoint caching we use Django's built-in ``django.core.cache``
# framework backed by ``django_redis.cache.RedisCache``.
#
# Key behaviour:
#   - IGNORE_EXCEPTIONS=True in settings.CACHES['default']['OPTIONS']
#     means a Redis outage silently returns None — NO exception, NO retry.
#   - This is the industry-standard pattern (Stripe, Shopify, Netflix):
#     cache miss → go straight to DB, return result, never block the user.
#   - We do NOT use ``get_redis_connection_safe()`` here (which has a 3-retry
#     loop) because that defeats the purpose — 3 × 500ms hangs = 1.5s delay.
#   - The 3-retry loop is intentionally kept for background tasks (presign
#     caching, OTP) where the small delay is acceptable and consistency matters.
#
# Usage in DRF / Django-Ninja views:
#   from apps.common.utils.redis import api_cache_get, api_cache_set
#
#   def my_view(request):
#       data = api_cache_get("products:featured")
#       if data is None:
#           data = list(Product.objects.filter(featured=True).values())
#           api_cache_set("products:featured", data, ttl=300)
#       return Response(data)
# ─────────────────────────────────────────────────────────────────────────────

def api_cache_get(key: str) -> Any:
    """
    Retrieve a cached API response from Django's default cache (Redis).

    On Redis miss OR Redis unavailability → returns ``None`` immediately.
    No retry, no delay.  Caller must then query the DB.

    Args:
        key: Cache key string. Use a consistent prefix scheme, e.g.
             ``"products:featured"`` or ``"vendor:{vid}:stats"``.

    Returns:
        Deserialized Python value, or ``None``.
    """
    from django.core.cache import cache
    try:
        return cache.get(key)
    except Exception as exc:
        # Should never reach here with IGNORE_EXCEPTIONS=True, but guard anyway
        logger.debug("api_cache_get: unexpected error for key=%s: %s", key, exc)
        return None


def api_cache_set(key: str, value: Any, ttl: int = 300) -> bool:
    """
    Store an API response in Django's default cache (Redis).

    On Redis unavailability → returns ``False`` silently.
    The API response has already been returned; the cache is best-effort.

    Args:
        key:   Cache key string.
        value: Any Django-cache-serializable Python object.
        ttl:   Time-to-live in seconds (default 5 minutes).

    Returns:
        ``True`` on success, ``False`` on Redis unavailability.
    """
    from django.core.cache import cache
    try:
        cache.set(key, value, timeout=ttl)
        return True
    except Exception as exc:
        logger.debug("api_cache_set: unexpected error for key=%s: %s", key, exc)
        return False


def api_cache_delete(key: str) -> bool:
    """
    Invalidate a cached API response.

    Call this after a write operation (POST/PUT/PATCH/DELETE) that mutates
    the data the cached key represents.

    Args:
        key: Cache key to delete.

    Returns:
        ``True`` on success, ``False`` on Redis unavailability.
    """
    from django.core.cache import cache
    try:
        cache.delete(key)
        return True
    except Exception as exc:
        logger.debug("api_cache_delete: unexpected error for key=%s: %s", key, exc)
        return False


def api_cache_delete_pattern(pattern: str) -> int:
    """
    Delete all Redis keys matching a glob pattern.

    Use for cache invalidation when a change affects multiple related keys,
    e.g. ``"products:*"`` after a product bulk-update.

    Implemented via ``django_redis``'s ``delete_pattern()`` extension,
    which is NOT available in the base Django cache API — falls back to 0
    if the backend does not support it.

    Args:
        pattern: Redis glob pattern, e.g. ``"vendor:abc123:*"``.

    Returns:
        Number of keys deleted (0 on failure or no matches).
    """
    try:
        from django.core.cache import cache
        return cache.delete_pattern(pattern)  # type: ignore[attr-defined]
    except AttributeError:
        # Non-Redis backend or older django-redis version
        logger.debug(
            "api_cache_delete_pattern: backend does not support delete_pattern()"
        )
        return 0
    except Exception as exc:
        logger.debug(
            "api_cache_delete_pattern: error for pattern=%s: %s", pattern, exc
        )
        return 0
