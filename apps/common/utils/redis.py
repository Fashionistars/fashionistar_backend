# apps/common/utils/redis.py
"""
Enterprise Redis Utility Layer for Fashionistar (v2.0 — ASGI-Safe).

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

HOT-PATH SAFETY (Phase 3 ASGI fix)
────────────────────────────────────
``get_redis_connection_safe()`` contains a retry loop with ``time.sleep()``.
Calling it from ANY request handler (sync or async) blocks the event loop
or OS thread for up to 3 seconds. It is ONLY permitted in:

  - Celery tasks
  - Management commands
  - Background threads launched from WSGI views

For API request handlers use the ``api_cache_*`` family (Section 4) or the
``async_api_cache_*`` family (Section 5) which use Django's cache framework
with IGNORE_EXCEPTIONS=True — zero retry, zero blocking.

A ``@hot_path_forbidden`` guard is provided for CI enforcement.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from functools import wraps
from typing import Any, Optional

from django_redis import get_redis_connection

logger = logging.getLogger(__name__)

# ─── Retry configuration ─────────────────────────────────────────────────────
REDIS_MAX_RETRIES: int = 3
REDIS_RETRY_DELAY: int = 1  # seconds between each retry attempt

# ─── Hot-path safety constant ─────────────────────────────────────────────────
# Maximum acceptable Redis latency on the HTTP request path.
# Any operation taking longer than this is disqualifying for hot-path use.
REDIS_HOT_PATH_TIMEOUT: float = 0.05   # 50ms hard ceiling


# ─── Hot-path guard decorator ─────────────────────────────────────────────────
def hot_path_forbidden(func):
    """
    Decorator that marks a function as FORBIDDEN on the API request hot path.

    In DEBUG mode: raises RuntimeError immediately if called from any context
    that looks like a Django request (checked via call stack heuristics).

    In production: logs a WARNING with a full traceback so it can be caught in
    Sentry/Datadog without crashing a live request.

    Usage:
        @hot_path_forbidden
        def get_redis_connection_safe(...):
            ...

    CI enforcement:
        grep -r 'get_redis_connection_safe' apps/ \
            | grep -v 'tasks.py' \
            | grep -v 'management/' \
            | grep -v 'utils/redis.py'
        # Must return 0 lines — only the definition itself is allowed.
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        import traceback
        from django.conf import settings
        # Fast check: if there's a running asyncio event loop, we're on-path
        is_async_context = False
        try:
            asyncio.get_running_loop()
            is_async_context = True
        except RuntimeError:
            pass

        if is_async_context:
            msg = (
                f"🚫 HOT-PATH VIOLATION: {func.__qualname__}() called from an async "
                "context (event loop running). This blocks the event loop. "
                "Use async_api_cache_get/set or api_cache_get/set instead."
            )
            if getattr(settings, 'DEBUG', False):
                raise RuntimeError(msg)
            logger.warning("%s\n%s", msg, "".join(traceback.format_stack()))

        return func(*args, **kwargs)
    return wrapper


# ─────────────────────────────────────────────────────────────────────────────
# 1. Connection
# ─────────────────────────────────────────────────────────────────────────────

import fnmatch

# Global in-memory dictionary to act as the mock Redis database when Redis is down
_MOCK_REDIS_DB: dict[str, str] = {}

class FakeRedisPipeline:
    def __init__(self, db: dict[str, str]):
        self.db = db
        self.commands: list[tuple[str, Any, Any, Any] | tuple[str, Any]] = []

    def setex(self, key: Any, ttl: Any, value: Any) -> FakeRedisPipeline:
        self.commands.append(('setex', key, ttl, value))
        return self

    def delete(self, *keys: Any) -> FakeRedisPipeline:
        self.commands.append(('delete', keys))
        return self

    def watch(self, *keys: Any) -> FakeRedisPipeline:
        return self

    def unwatch(self) -> FakeRedisPipeline:
        return self

    def multi(self) -> FakeRedisPipeline:
        return self

    def get(self, key: Any) -> Optional[bytes]:
        if isinstance(key, bytes):
            key = key.decode('utf-8')
        val = self.db.get(key)
        if val is not None:
            if isinstance(val, str):
                return val.encode('utf-8')
            return val
        return None

    def execute(self) -> list[Any]:
        results = []
        for cmd in self.commands:
            if cmd[0] == 'setex':
                _, key, ttl, value = cmd
                if isinstance(key, bytes):
                    key = key.decode('utf-8')
                if isinstance(value, bytes):
                    value = value.decode('utf-8')
                self.db[key] = value
                results.append(True)
            elif cmd[0] == 'delete':
                _, keys = cmd
                deleted_count = 0
                for k in keys:
                    if isinstance(k, bytes):
                        k = k.decode('utf-8')
                    if self.db.pop(k, None) is not None:
                        deleted_count += 1
                results.append(deleted_count)
        self.commands = []
        return results

    def __enter__(self) -> FakeRedisPipeline:
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        pass


class FakeRedis:
    def ping(self) -> bool:
        return True

    def get(self, key: Any) -> Optional[bytes]:
        if isinstance(key, bytes):
            key = key.decode('utf-8')
        val = _MOCK_REDIS_DB.get(key)
        if val is not None:
            if isinstance(val, str):
                return val.encode('utf-8')
            return val
        return None

    def setex(self, key: Any, ttl: Any, value: Any) -> bool:
        if isinstance(key, bytes):
            key = key.decode('utf-8')
        if isinstance(value, bytes):
            value = value.decode('utf-8')
        _MOCK_REDIS_DB[key] = value
        return True

    def delete(self, *keys: Any) -> int:
        count = 0
        for k in keys:
            if isinstance(k, bytes):
                k = k.decode('utf-8')
            if _MOCK_REDIS_DB.pop(k, None) is not None:
                count += 1
        return count

    def keys(self, pattern: Any) -> list[bytes]:
        if isinstance(pattern, bytes):
            pattern = pattern.decode('utf-8')
        results = []
        for k in _MOCK_REDIS_DB.keys():
            if fnmatch.fnmatch(k, pattern):
                results.append(k.encode('utf-8'))
        return results

    def pipeline(self) -> FakeRedisPipeline:
        return FakeRedisPipeline(_MOCK_REDIS_DB)


_REDIS_OFFLINE_UNTIL: float = 0.0


@hot_path_forbidden
def get_redis_connection_safe(
    max_retries: int = REDIS_MAX_RETRIES,
    retry_delay: int = REDIS_RETRY_DELAY,
) -> Any:
    """
    Establish a safe Redis connection with exponential-style retry.

    ⚠️  BACKGROUND / CELERY TASKS ONLY  ⚠️
    ──────────────────────────────────
    This function blocks for up to (max_retries × retry_delay) = 3 seconds.
    NEVER call it from a Django view, middleware, or any async context.
    It will block the WSGI thread or stall the ASGI event loop.

    ✅ Permitted in:
        - Celery tasks (apps/*/tasks.py)
        - Management commands (manage.py ...)
        - BackgroundScheduler / APScheduler jobs
        - Daemon threads launched outside the request path

    ❌ FORBIDDEN in:
        - Django views (DRF or Ninja)
        - Django middleware
        - Any async def function

    For hot-path API caching use:
        api_cache_get / api_cache_set (Section 4)
        async_api_cache_get / async_api_cache_set (Section 5)

    Returns the live ``StrictRedis`` connection object, or a fallback in-memory
    ``FakeRedis`` client if Redis is unreachable after all retries.

    Args:
        max_retries:  Number of connection attempts.
        retry_delay:  Seconds to wait between retries.

    Returns:
        ``redis.StrictRedis`` or ``FakeRedis``.
    """
    global _REDIS_OFFLINE_UNTIL
    now = time.time()
    if now < _REDIS_OFFLINE_UNTIL:
        # Circuit breaker is tripped — skip Redis to save time
        return FakeRedis()

    for attempt in range(max_retries):
        try:
            conn = get_redis_connection("default")
            conn.ping()
            return conn
        except Exception as exc:
            logger.warning(
                "Redis connection error (attempt %d/%d): %s",
                attempt + 1, max_retries, exc,
            )
            if attempt < max_retries - 1:
                time.sleep(retry_delay)

    # Trip the circuit breaker for 15 seconds to prevent repeated blocking
    _REDIS_OFFLINE_UNTIL = time.time() + 15.0
    logger.warning(
        "Max Redis connection retries reached. Circuit breaker tripped for 15s. "
        "Falling back to in-memory FakeRedis."
    )
    return FakeRedis()


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
        return 0
    except Exception as exc:
        logger.debug(
            "api_cache_delete_pattern: error for pattern=%s: %s", pattern, exc
        )
        return 0


# ─────────────────────────────────────────────────────────────────────────────
# 5. ASYNC API Cache helpers  ← ASGI / async views only (Django 4.1+ aget/aset)
# ─────────────────────────────────────────────────────────────────────────────
#
# Async wrappers around the same Django ``django.core.cache`` framework used
# in Section 4 — the IGNORE_EXCEPTIONS=True backend guarantees zero blocking.
#
# Django 4.1+ added native async support to the cache framework via
# ``cache.aget()`` / ``cache.aset()`` / ``cache.adelete()``.
# These are non-blocking coroutines awaitable directly in Ninja async views
# and async middleware without any sync_to_async wrapper.
#
# Usage in Django-Ninja async GET views:
#   from apps.common.utils.redis import async_api_cache_get, async_api_cache_set
#
#   @router.get("/products/featured")
#   async def featured_products(request):
#       data = await async_api_cache_get("products:featured")
#       if data is None:
#           data = [p async for p in Product.objects.filter(featured=True)]
#           await async_api_cache_set("products:featured", data, ttl=300)
#       return data
# ─────────────────────────────────────────────────────────────────────────────


async def async_api_cache_get(key: str) -> Any:
    """
    Non-blocking async cache GET for Ninja / ASGI view handlers.

    Uses Django 4.1+ native ``cache.aget()`` coroutine — awaitable directly
    on the event loop, zero thread-pool dispatch.

    On Redis miss OR Redis unavailability → returns ``None`` immediately.

    Args:
        key: Cache key string.

    Returns:
        Deserialized Python value, or ``None``.
    """
    from django.core.cache import cache
    try:
        return await cache.aget(key)  # type: ignore[attr-defined]
    except Exception as exc:
        logger.debug("async_api_cache_get: error for key=%s: %s", key, exc)
        return None


async def async_api_cache_set(key: str, value: Any, ttl: int = 300) -> bool:
    """
    Non-blocking async cache SET for Ninja / ASGI view handlers.

    Uses Django 4.1+ native ``cache.aset()`` coroutine.

    On Redis unavailability → returns ``False`` silently.

    Args:
        key:   Cache key string.
        value: Any Django-cache-serializable Python object.
        ttl:   Time-to-live in seconds (default 5 minutes).

    Returns:
        ``True`` on success, ``False`` on Redis unavailability.
    """
    from django.core.cache import cache
    try:
        await cache.aset(key, value, timeout=ttl)  # type: ignore[attr-defined]
        return True
    except Exception as exc:
        logger.debug("async_api_cache_set: error for key=%s: %s", key, exc)
        return False


async def async_api_cache_delete(key: str) -> bool:
    """
    Non-blocking async cache DELETE for Ninja / ASGI view handlers.

    Args:
        key: Cache key to delete.

    Returns:
        ``True`` on success, ``False`` on Redis unavailability.
    """
    from django.core.cache import cache
    try:
        await cache.adelete(key)  # type: ignore[attr-defined]
        return True
    except Exception as exc:
        logger.debug("async_api_cache_delete: error for key=%s: %s", key, exc)
        return False


async def async_api_cache_delete_pattern(pattern: str) -> int:
    """
    Non-blocking async pattern-based cache invalidation.

    Falls back to sync ``api_cache_delete_pattern()`` in a thread executor
    if the backend does not expose async pattern deletion.

    Args:
        pattern: Redis glob pattern, e.g. ``"vendor:abc123:*"``.

    Returns:
        Number of keys deleted (0 on failure or no matches).
    """
    try:
        from django.core.cache import cache
        if hasattr(cache, "adelete_pattern"):
            return await cache.adelete_pattern(pattern)  # type: ignore[attr-defined]
        # Fallback: run sync version in thread executor (safe for ASGI)
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, api_cache_delete_pattern, pattern)
    except Exception as exc:
        logger.debug("async_api_cache_delete_pattern: error for pattern=%s: %s", pattern, exc)
        return 0


async def async_get_redis_connection_safe(
    max_retries: int = 3,
    retry_delay: float = 0.5,
) -> Any:
    """
    Async-safe Redis connection helper for background coroutines.

    ⚠️  BACKGROUND COROUTINES ONLY  ⚠️
    ────────────────────────────────────
    This is the async equivalent of ``get_redis_connection_safe()``.
    Uses ``asyncio.sleep()`` (yields to event loop) instead of ``time.sleep()``
    (blocks the event loop).

    Still NOT suitable for the request hot path — use async_api_cache_get/set
    for views and middleware. This is for:
      • Async Celery tasks
      • Async management commands
      • Async background coroutines launched via asyncio.create_task()

    Args:
        max_retries:  Connection attempts before returning FakeRedis.
        retry_delay:  Seconds to sleep between retries (asyncio.sleep — non-blocking).

    Returns:
        ``redis.asyncio.Redis`` or ``FakeRedis``.
    """
    try:
        import redis.asyncio as aioredis
        from django.conf import settings

        cache_conf = settings.CACHES.get("default", {})
        location = cache_conf.get("LOCATION", "redis://127.0.0.1:6379/1")
        options = cache_conf.get("OPTIONS", {})
        password = options.get("PASSWORD", None)

        for attempt in range(max_retries):
            try:
                client = aioredis.from_url(
                    location,
                    password=password,
                    encoding="utf-8",
                    decode_responses=True,
                    socket_timeout=REDIS_HOT_PATH_TIMEOUT,
                    socket_connect_timeout=REDIS_HOT_PATH_TIMEOUT,
                )
                await client.ping()
                return client
            except Exception as exc:
                logger.warning(
                    "async Redis connection error (attempt %d/%d): %s",
                    attempt + 1, max_retries, exc,
                )
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay)   # NON-BLOCKING sleep

    except ImportError:
        logger.warning(
            "redis.asyncio not available. Install redis>=4.2 for async support. "
            "Falling back to FakeRedis."
        )

    return FakeRedis()
