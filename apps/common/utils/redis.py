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

# Key template: cloudinary:presign:{user_id}:{asset_type}
_PRESIGN_KEY = "cloudinary:presign:{user_id}:{asset_type}"
_PRESIGN_TTL = 3300  # 55 minutes — slightly less than the 1-hour signature validity


def cache_upload_presign(user_id: str, asset_type: str, params: dict) -> bool:
    """
    Cache a Cloudinary pre-signed upload parameter set in Redis.

    Key format: ``cloudinary:presign:{user_id}:{asset_type}``
    TTL:        3300 seconds (55 minutes)

    Args:
        user_id:    The UUID string of the requesting user.
        asset_type: One of ``avatar``, ``product_image``, ``product_video``,
                    ``measurement``.
        params:     Dict of presign params returned by Cloudinary signature
                    generation (cloud_name, api_key, signature, timestamp, …).

    Returns:
        ``True`` on success, ``False`` if Redis is unavailable.
    """
    conn = get_redis_connection_safe()
    if conn is None:
        return False
    try:
        key = _PRESIGN_KEY.format(user_id=user_id, asset_type=asset_type)
        conn.setex(key, _PRESIGN_TTL, json.dumps(params))
        logger.debug("Presign cached for user=%s asset=%s", user_id, asset_type)
        return True
    except Exception as exc:
        logger.warning("Failed to cache presign for user=%s: %s", user_id, exc)
        return False


def get_cached_presign(user_id: str, asset_type: str) -> Optional[dict]:
    """
    Retrieve cached Cloudinary presign params from Redis.

    Returns:
        The cached params dict, or ``None`` on miss / Redis unavailability.
    """
    conn = get_redis_connection_safe()
    if conn is None:
        return None
    try:
        key = _PRESIGN_KEY.format(user_id=user_id, asset_type=asset_type)
        raw = conn.get(key)
        if raw:
            logger.debug("Presign cache HIT for user=%s asset=%s", user_id, asset_type)
            return json.loads(raw)
        return None
    except Exception as exc:
        logger.warning("Failed to read presign cache for user=%s: %s", user_id, exc)
        return None


def invalidate_upload_presign(user_id: str, asset_type: str) -> bool:
    """
    Invalidate (delete) a cached presign token for the given user + asset type.

    Call this after a successful upload confirmation so the next upload request
    generates a fresh signature rather than reusing the old one.
    """
    conn = get_redis_connection_safe()
    if conn is None:
        return False
    try:
        key = _PRESIGN_KEY.format(user_id=user_id, asset_type=asset_type)
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
