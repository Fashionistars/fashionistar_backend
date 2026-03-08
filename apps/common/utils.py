# apps/common/utils.py
import asyncio
import time
import random
import logging
import base64
import datetime
from dataclasses import dataclass
from typing import Optional, Any
from django.conf import settings
from cryptography.fernet import Fernet
from django_redis import get_redis_connection
import cloudinary.uploader
import cloudinary.api
from django.utils import timezone

application_logger = logging.getLogger(__name__)

# ============================================================================
# INITIALIZATION
# ============================================================================

# Initialize Fernet cipher suite for OTP encryption/decryption
try:
    base_key = settings.SECRET_KEY.encode()
    # Pad or truncate to ensure 32 bytes for Fernet
    base_key = base_key.ljust(32, b'\0')[:32]
    cipher_suite = Fernet(base64.urlsafe_b64encode(base_key))
except Exception as e:
    application_logger.critical(f"Failed to initialize encryption key: {e}")
    cipher_suite = None

# Retry settings for Redis connection
REDIS_MAX_RETRIES: int = 3
REDIS_RETRY_DELAY: int = 1  # seconds


# ============================================================================
# CRYPTOGRAPHY UTLITIES
# ============================================================================

def encrypt_otp(otp: str) -> str:
    """
    Encrypts the given OTP using Fernet.
    
    Args:
        otp (str): The plain text OTP.
        
    Returns:
        str: Encrypted OTP string.

    Raises:
        RuntimeError: If encryption suite is not initialized.
    """
    if not cipher_suite:
         raise RuntimeError("Encryption suite not initialized")
    try:
        return cipher_suite.encrypt(otp.encode()).decode()
    except Exception as e:
        application_logger.error(f"OTP encryption failed: {e}")
        raise

def decrypt_otp(encrypted_otp: str) -> str:
    """
    Decrypts the given encrypted OTP using Fernet.

    Args:
        encrypted_otp (str): The encrypted OTP string.

    Returns:
        str: Decrypted OTP string.

    Raises:
        RuntimeError: If encryption suite is not initialized.
    """
    if not cipher_suite:
         raise RuntimeError("Encryption suite not initialized")
    try:
        return cipher_suite.decrypt(encrypted_otp.encode()).decode()
    except Exception as e:
        application_logger.error(f"OTP decryption failed: {e}")
        raise


# ============================================================================
# REDIS UTILITIES
# ============================================================================

def get_redis_connection_safe(max_retries: int = REDIS_MAX_RETRIES, retry_delay: int = REDIS_RETRY_DELAY) -> Optional[Any]:
    """
    Establishes a safe connection to Redis with retry mechanism.

    Args:
        max_retries (int): Number of connection attempts.
        retry_delay (int): Seconds to wait between retries.

    Returns:
        redis.StrictRedis or None: Active Redis connection or None if failed.
    """
    for attempt in range(max_retries):
        try:
            redis_conn = get_redis_connection("default")
            redis_conn.ping()  # Ensure Redis is available
            return redis_conn
        except Exception as e:
            application_logger.error(f"Redis connection error (attempt {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                time.sleep(retry_delay)  # Wait before retrying
            else:
                application_logger.error("Max Redis connection retries reached. Redis unavailable.")
                return None
    return None


# ============================================================================
# GENERATION UTILITIES
# ============================================================================

def generate_numeric_otp(length: int = 6) -> str:
    """
    Generates a numeric OTP of the specified length.
    
    Args:
        length (int): Length of OTP.
        
    Returns:
        str: Numeric OTP string.
    """
    return ''.join(random.choices('0123456789', k=length))


def get_otp_expiry_datetime() -> datetime.datetime:
    """
    Calculates the OTP expiry datetime (5 minutes from now).

    Returns:
        datetime: A timezone-aware datetime object representing the expiry time.
    """
    from django.utils import timezone
    return timezone.now() + datetime.timedelta(seconds=300)


def user_directory_path(instance, filename) -> str:
    """
    Generate an optimized, role-separated file path for a given user directory.
    Matches Cloudinary modern layout expectations, with full domain separation
    (Users, Products, Vendors, Categories, Brands) and RBAC accountability.
    """
    import time
    from django.core.exceptions import ValidationError

    try:
        user = None
        domain = 'other'

        # 1. Determine root domain based on the instance's class name
        model_name = instance.__class__.__name__.lower()
        if 'product' in model_name:
            domain = 'products'
        elif 'vendor' in model_name:
            domain = 'vendors'
        elif 'category' in model_name:
            domain = 'categories'
        elif 'brand' in model_name:
            domain = 'brands'
        elif 'user' in model_name or 'profile' in model_name:
            domain = 'users'

        # 2. Extract the associated user for accountability mapping
        if hasattr(instance, 'user') and instance.user:
            user = instance.user
        elif hasattr(instance, 'vendor') and hasattr(instance.vendor, 'user') and instance.vendor.user:
            user = instance.vendor.user
        elif hasattr(instance, 'product') and hasattr(instance.product, 'vendor') and hasattr(instance.product.vendor, 'user'):
            user = getattr(instance.product.vendor, 'user', None)

        # 3. Handle Role-Based Access Control Segregation
        role_folder = "general"
        if user and hasattr(user, 'role') and user.role:
            role = str(user.role).lower()
            if role in ['admin', 'staff', 'support', 'reviewer', 'assistant']:
                role_folder = 'internal_staff'
            elif role == 'vendor':
                role_folder = 'vendors'
            elif role == 'client':
                role_folder = 'clients'

        # 4. Construct a latency-friendly path structure
        ext = filename.split('.')[-1] if '.' in filename else ''
        safe_filename = f"{getattr(instance, 'pk', 'new')}_{int(time.time())}.{ext}" if ext else f"{getattr(instance, 'pk', 'new')}_{int(time.time())}"

        if user:
            return f"uploads/{role_folder}/{domain}/user_{user.id}/{safe_filename}"
        else:
            return f"uploads/system/{domain}/general/{safe_filename}"

    except Exception as e:
        raise ValidationError(f"Error generating optimized file path: {str(e)}")


# ============================================================================
# CLOUDINARY UTILITIES
# ============================================================================

def delete_cloudinary_asset(public_id: str, resource_type: str = "image") -> Optional[dict]:
    """
    Deletes an asset from Cloudinary synchronously.
    """
    try:
        if not public_id:
            return None
        result = cloudinary.uploader.destroy(public_id, resource_type=resource_type)
        application_logger.info(f"Cloudinary asset {public_id} deletion result: {result}")
        return result
    except Exception as e:
        application_logger.error(f"Error deleting Cloudinary asset {public_id}: {e}")
        return None

def delete_cloudinary_asset_async(public_id: str, resource_type: str = "image"):
    """
    Dispatches a background Celery task to delete a Cloudinary asset.
    Makes file deletions transaction-atomic and completely non-blocking
    for the main event loop to reduce latency.
    """
    if not public_id:
        return

    from django.db import transaction
    from apps.common.tasks import delete_cloudinary_asset_task

    def _fire():
        try:
            delete_cloudinary_asset_task.apply_async(
                args=[public_id],
                kwargs={"resource_type": resource_type},
                retry=False,
                ignore_result=True
            )
        except Exception as e:
            application_logger.warning(f"Broker unavailable — fallback to sync delete for {public_id}. Error: {e}")
            delete_cloudinary_asset(public_id, resource_type)

    # Fire ONLY after DB transaction commits successfully
    transaction.on_commit(_fire)


# ============================================================================
# ASYNC CLOUDINARY BULK UTILITIES
# ============================================================================
# All functions below offload blocking Cloudinary SDK calls to thread pool
# via asyncio.to_thread() — no sync_to_async, no event-loop stalls.
#
# Frontend (Next.js) note:
#   - Set "upload_preset" for unsigned direct-browser uploading.
#   - Return `secure_url`, `public_id`, and `resource_type` in all responses
#     so the frontend can immediately render without a second round-trip.
# ============================================================================

@dataclass
class CloudinaryUploadResult:
    """Canonical result container for one media asset upload."""
    file_path: str
    public_id: str = ""
    secure_url: str = ""
    resource_type: str = "image"
    width: int = 0
    height: int = 0
    format: str = ""
    bytes: int = 0
    duration: float = 0.0   # seconds (video only)
    success: bool = False
    error: str = ""


@dataclass
class CloudinaryDeleteResult:
    """Canonical result container for one media deletion."""
    public_id: str
    resource_type: str = "image"
    result: str = ""          # "ok" | "not found"
    success: bool = False
    error: str = ""


def _sync_upload_one(
    file_path: str,
    folder: str,
    resource_type: str,
    transformation: list | None,
    eager: list | None,
) -> CloudinaryUploadResult:
    """Synchronous Cloudinary upload — runs inside asyncio.to_thread()."""
    try:
        upload_kwargs: dict = {
            "folder": folder,
            "resource_type": resource_type,
            "use_filename": True,
            "unique_filename": True,
            "overwrite": False,
            "quality": "auto",
            "fetch_format": "auto",
        }
        if transformation:
            upload_kwargs["transformation"] = transformation
        if eager:
            upload_kwargs["eager"] = eager
            upload_kwargs["eager_async"] = True  # process eagerly in background

        res = cloudinary.uploader.upload(file_path, **upload_kwargs)
        return CloudinaryUploadResult(
            file_path=file_path,
            public_id=res.get("public_id", ""),
            secure_url=res.get("secure_url", ""),
            resource_type=res.get("resource_type", resource_type),
            width=res.get("width", 0),
            height=res.get("height", 0),
            format=res.get("format", ""),
            bytes=res.get("bytes", 0),
            duration=float(res.get("duration", 0)),
            success=True,
        )
    except Exception as exc:
        application_logger.error(f"Cloudinary upload failed [{file_path}]: {exc}")
        return CloudinaryUploadResult(file_path=file_path, error=str(exc), success=False)


async def async_bulk_upload_media(
    file_paths: list[str],
    *,
    folder: str = "fashionistar/uploads",
    resource_type: str = "auto",
    transformation: list | None = None,
    eager: list | None = None,
    max_concurrency: int = 10,
) -> list[CloudinaryUploadResult]:
    """
    Upload multiple media files (images + videos) to Cloudinary concurrently.

    Enterprise design decisions:
    - `asyncio.Semaphore` caps concurrent SDK calls to `max_concurrency`
      (default 10). Cloudinary free plans allow ~500 req/min; adjust for paid.
    - Each upload runs in `asyncio.to_thread()` so the ASGI event loop is NEVER
      blocked regardless of file size or network latency.
    - `eager` transformations are queued asynchronously server-side via
      `eager_async=True`, avoiding upload-time CPU overhead.
    - Results preserve insertion order matching input `file_paths`.

    Args:
        file_paths:      Absolute local file paths or remote URLs.
        folder:          Cloudinary folder prefix.
        resource_type:   "image" | "video" | "raw" | "auto" (recommended).
        transformation:  Cloudinary eager-transform specs.
        eager:           Additional eager transformation specs.
        max_concurrency: Max simultaneous SDK calls.

    Returns:
        List[CloudinaryUploadResult] preserving input order.
    """
    sem = asyncio.Semaphore(max_concurrency)

    async def _upload_one_guarded(fp: str) -> CloudinaryUploadResult:
        async with sem:
            return await asyncio.to_thread(
                _sync_upload_one, fp, folder, resource_type, transformation, eager
            )

    tasks = [asyncio.create_task(_upload_one_guarded(fp)) for fp in file_paths]
    results = await asyncio.gather(*tasks, return_exceptions=False)

    success = sum(1 for r in results if r.success)
    application_logger.info(
        f"async_bulk_upload_media: {success}/{len(file_paths)} succeeded "
        f"into folder '{folder}'"
    )
    return list(results)


def _sync_delete_one(public_id: str, resource_type: str) -> CloudinaryDeleteResult:
    """Synchronous Cloudinary deletion — runs inside asyncio.to_thread()."""
    try:
        res = cloudinary.uploader.destroy(public_id, resource_type=resource_type)
        ok = res.get("result") == "ok"
        return CloudinaryDeleteResult(
            public_id=public_id,
            resource_type=resource_type,
            result=res.get("result", ""),
            success=ok,
            error="" if ok else res.get("result", "unknown"),
        )
    except Exception as exc:
        application_logger.error(f"Cloudinary delete failed [{public_id}]: {exc}")
        return CloudinaryDeleteResult(public_id=public_id, resource_type=resource_type,
                                      error=str(exc), success=False)


async def async_bulk_delete_media(
    public_ids: list[str],
    *,
    resource_type: str = "image",
    max_concurrency: int = 20,
) -> list[CloudinaryDeleteResult]:
    """
    Delete multiple Cloudinary assets concurrently without blocking the event loop.

    Enterprise notes:
    - Higher default concurrency (20) vs uploads because DELETE requests are
      lightweight (no payload, no streaming).
    - Each call still uses asyncio.to_thread() to prevent SDK blocking.
    - Also calls Cloudinary's bulk `delete_resources` when the batch is large
      (> 100 items) for a 10x speedup via their batch API.

    Args:
        public_ids:      List of Cloudinary public_ids to delete.
        resource_type:   "image" | "video" | "raw".
        max_concurrency: Max simultaneous SDK calls.

    Returns:
        List[CloudinaryDeleteResult] preserving input order.
    """
    if not public_ids:
        return []

    # Use Cloudinary's batch delete API for large sets (max 100 per call)
    if len(public_ids) > 50:
        async def _batch_delete(batch: list[str]) -> list[CloudinaryDeleteResult]:
            def _sync_batch():
                return cloudinary.api.delete_resources(
                    batch, resource_type=resource_type, invalidate=True
                )
            res = await asyncio.to_thread(_sync_batch)
            deleted = res.get("deleted", {})
            return [
                CloudinaryDeleteResult(
                    public_id=pid,
                    resource_type=resource_type,
                    result=deleted.get(pid, "not found"),
                    success=deleted.get(pid) == "deleted",
                )
                for pid in batch
            ]

        import cloudinary.api
        sem = asyncio.Semaphore(5)   # Cloudinary rate-limit: only a few batch calls simultaneously
        chunk_size = 100

        async def _guarded_batch(batch: list[str]):
            async with sem:
                return await _batch_delete(batch)

        chunks = [public_ids[i:i+chunk_size] for i in range(0, len(public_ids), chunk_size)]
        chunk_results = await asyncio.gather(*[asyncio.create_task(_guarded_batch(c)) for c in chunks])
        results = [item for sublist in chunk_results for item in sublist]
    else:
        sem = asyncio.Semaphore(max_concurrency)

        async def _delete_one_guarded(pid: str) -> CloudinaryDeleteResult:
            async with sem:
                return await asyncio.to_thread(_sync_delete_one, pid, resource_type)

        tasks = [asyncio.create_task(_delete_one_guarded(pid)) for pid in public_ids]
        results = await asyncio.gather(*tasks, return_exceptions=False)

    success = sum(1 for r in results if r.success)
    application_logger.info(
        f"async_bulk_delete_media: {success}/{len(public_ids)} deleted "
        f"(resource_type={resource_type})"
    )
    return list(results)


async def async_get_media_info_bulk(
    public_ids: list[str],
    *,
    resource_type: str = "image",
    max_concurrency: int = 20,
) -> list[dict]:
    """
    Retrieve metadata for a bulk list of Cloudinary assets concurrently.
    Useful for the Next.js frontend to pre-generate responsive image sizes
    (width/height from Cloudinary) without a dedicated DB column.

    Returns:
        List of raw Cloudinary resource dicts (or error dicts).
    """
    import cloudinary.api

    sem = asyncio.Semaphore(max_concurrency)

    async def _fetch_one(pid: str) -> dict:
        async with sem:
            def _sync():
                try:
                    return cloudinary.api.resource(pid, resource_type=resource_type)
                except Exception as exc:
                    return {"public_id": pid, "error": str(exc)}
            return await asyncio.to_thread(_sync)

    tasks = [asyncio.create_task(_fetch_one(pid)) for pid in public_ids]
    return list(await asyncio.gather(*tasks))
