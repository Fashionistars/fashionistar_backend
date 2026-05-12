# apps/common/utils/__init__.py
"""
``apps.common.utils`` package.

Backward-Compatibility Re-exports
──────────────────────────────────
Every symbol that was previously importable from the old monolithic
``apps.common.utils`` module is re-exported here, so that **zero existing
imports** need to change across the codebase.

Sub-module layout:
    redis.py      — Redis connection pool, presign caching, OTP store.
    cloudinary.py — Pre-sign generation, transform URLs, async bulk ops.
    helpers.py    — OTP crypto, OTP generation, user_directory_path.
"""

# ── Redis utilities ───────────────────────────────────────────────────────────
from apps.common.utils.redis import (       # noqa: F401
    get_redis_connection_safe,
    cache_upload_presign,
    get_cached_presign,
    invalidate_upload_presign,
    redis_set,
    redis_get,
    redis_delete,
    redis_incr,
    REDIS_MAX_RETRIES,
    REDIS_RETRY_DELAY,
    # Single-try API endpoint caching (no retry loop)
    api_cache_get,
    api_cache_set,
    api_cache_delete,
    api_cache_delete_pattern,
)

# ── Cloudinary utilities ──────────────────────────────────────────────────────
from apps.common.utils.cloudinary import (  # noqa: F401
    # Dataclasses / result containers
    CloudinaryUploadResult,
    CloudinaryDeleteResult,
    CloudinaryPresignResult,

    # Pre-sign (Phase 1 of the two-phase upload pattern)
    generate_cloudinary_signature,
    generate_cloudinary_upload_params,

    # URL builder (2K / 4K / 8K support)
    get_cloudinary_transform_url,

    # Webhook validation
    validate_cloudinary_webhook,

    # Sync delete (for Celery workers)
    delete_cloudinary_asset,
    delete_cloudinary_asset_async,

    # Async bulk ops (ASGI / batch processing)
    async_bulk_upload_media,
    async_bulk_delete_media,
    async_get_media_info_bulk,
)

# ── General helpers ───────────────────────────────────────────────────────────
from apps.common.utils.helpers import (     # noqa: F401
    encrypt_otp,
    decrypt_otp,
    generate_numeric_otp,
    get_otp_expiry_datetime,
    user_directory_path,
    cipher_suite,
)

__all__ = [
    # Redis
    "get_redis_connection_safe",
    "cache_upload_presign",
    "get_cached_presign",
    "invalidate_upload_presign",
    "redis_set",
    "redis_get",
    "redis_delete",
    "redis_incr",
    "REDIS_MAX_RETRIES",
    "REDIS_RETRY_DELAY",
    # API endpoint cache (single-try)
    "api_cache_get",
    "api_cache_set",
    "api_cache_delete",
    "api_cache_delete_pattern",
    # Cloudinary
    "CloudinaryUploadResult",
    "CloudinaryDeleteResult",
    "CloudinaryPresignResult",
    "generate_cloudinary_signature",
    "generate_cloudinary_upload_params",
    "get_cloudinary_transform_url",
    "validate_cloudinary_webhook",
    "delete_cloudinary_asset",
    "delete_cloudinary_asset_async",
    "async_bulk_upload_media",
    "async_bulk_delete_media",
    "async_get_media_info_bulk",
    # Helpers
    "encrypt_otp",
    "decrypt_otp",
    "generate_numeric_otp",
    "get_otp_expiry_datetime",
    "user_directory_path",
    "cipher_suite",
]
