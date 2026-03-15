# apps/common/utils/cloudinary.py
"""
Enterprise Cloudinary Integration Layer for Fashionistar.

Architecture (Two-Phase Direct Upload Pattern)
──────────────────────────────────────────────
Phase 1 — PRE-SIGN:
    Backend generates a one-time HMAC-SHA256 signed upload parameter set.
    The signature is valid for ``CLOUDINARY_SIGNATURE_TTL`` seconds (default 1h).
    Signed params are cached in Redis to avoid re-signing on every page load.

Phase 2 — DIRECT UPLOAD (client-side):
    Frontend POSTs the file DIRECTLY to Cloudinary:
        POST https://api.cloudinary.com/v1_1/{cloud_name}/image/upload
    Django backend is NEVER in the upload path — no blocking I/O, no DNS hangs.

Phase 3 — CONFIRM:
    Cloudinary calls our webhook (``/api/v2/upload/webhook/cloudinary/``)
    with the full asset metadata (secure_url, public_id, bytes, width, height).
    A Celery task saves the ``secure_url`` to the appropriate model field.

Resolution Support
──────────────────
All product and measurement images support 2K / 4K / 8K delivery through
Cloudinary URL-based transformations. The ``get_cloudinary_transform_url()``
function builds these on the fly — no server-side processing required.

    2K  → width=2560, quality=auto
    4K  → width=3840, quality=auto
    8K  → width=7680, quality=auto

Next.js Integration
───────────────────
Use ``NEXT_PUBLIC_CLOUDINARY_CLOUD_NAME`` env var in Next.js and point
``next/image`` ``loader`` to ``get_cloudinary_transform_url()``-style URLs.
Example Next.js loader:

    const cloudinaryLoader = ({ src, width, quality }) =>
        `https://res.cloudinary.com/{cloud_name}/image/upload/f_auto,q_${quality||'auto'},w_${width}/${src}`;
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Optional

import cloudinary.api
import cloudinary.uploader
from django.conf import settings

logger = logging.getLogger(__name__)

# ─── Asset type → folder/preset mapping ──────────────────────────────────────
_ASSET_CONFIGS: dict[str, dict] = {
    "avatar": {
        "folder_prefix": "fashionistar/users/avatars",
        "preset_setting": "CLOUDINARY_UPLOAD_PRESET_AVATAR",
        "resource_type": "image",
        "eager": [
            {"width": 400,  "height": 400,  "crop": "fill", "quality": "auto", "fetch_format": "auto"},
            {"width": 150,  "height": 150,  "crop": "fill", "quality": "auto", "fetch_format": "auto"},
        ],
    },
    "product_image": {
        "folder_prefix": "fashionistar/products/images",
        "preset_setting": "CLOUDINARY_UPLOAD_PRESET_PRODUCT",
        "resource_type": "image",
        "eager": [
            {"width": 1200, "height": 1200, "crop": "fill", "quality": "auto", "fetch_format": "auto"},
            {"width": 800,  "height": 800,  "crop": "fill", "quality": "auto", "fetch_format": "auto"},
            {"width": 400,  "height": 400,  "crop": "fill", "quality": "auto", "fetch_format": "auto"},
            # 4K variant
            {"width": 3840, "crop": "scale", "quality": "auto", "fetch_format": "auto"},
        ],
    },
    "product_video": {
        "folder_prefix": "fashionistar/products/videos",
        "preset_setting": "CLOUDINARY_UPLOAD_PRESET_VIDEO",
        "resource_type": "video",
        "eager": [
            {"format": "mp4",  "quality": "auto", "width": 1920},
            {"format": "webm", "quality": "auto", "width": 1920},
            {"format": "mp4",  "quality": "auto", "width": 1280},  # 720p fallback
        ],
    },
    "measurement": {
        "folder_prefix": "fashionistar/measurements",
        "preset_setting": "CLOUDINARY_UPLOAD_PRESET_MEASURE",
        "resource_type": "image",
        "eager": [
            {"width": 2560, "crop": "scale", "quality": "auto", "fetch_format": "auto"},  # 2K
            {"width": 1920, "crop": "scale", "quality": "auto", "fetch_format": "auto"},  # FHD
            {"width": 800,  "crop": "scale", "quality": "auto", "fetch_format": "auto"},  # thumbnail
        ],
    },
}


# ─────────────────────────────────────────────────────────────────────────────
# Result dataclasses
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class CloudinaryUploadResult:
    """Canonical result container for one media asset upload."""
    file_path:     str
    public_id:     str  = ""
    secure_url:    str  = ""
    resource_type: str  = "image"
    width:         int  = 0
    height:        int  = 0
    format:        str  = ""
    bytes:         int  = 0
    duration:      float = 0.0   # seconds — video only
    success:       bool = False
    error:         str  = ""


@dataclass
class CloudinaryDeleteResult:
    """Canonical result container for one media deletion."""
    public_id:     str
    resource_type: str  = "image"
    result:        str  = ""          # "ok" | "not found"
    success:       bool = False
    error:         str  = ""


@dataclass
class CloudinaryPresignResult:
    """Presign token for client-side direct upload."""
    cloud_name:     str
    api_key:        str
    signature:      str
    timestamp:      int
    folder:         str
    upload_preset:  str
    resource_type:  str
    eager:          list = field(default_factory=list)
    eager_async:    bool = True
    success:        bool = True
    error:          str  = ""

    def to_dict(self) -> dict:
        return {
            "cloud_name":    self.cloud_name,
            "api_key":       self.api_key,
            "signature":     self.signature,
            "timestamp":     self.timestamp,
            "folder":        self.folder,
            "upload_preset": self.upload_preset,
            "resource_type": self.resource_type,
            "eager":         self.eager,
            "eager_async":   self.eager_async,
        }


# ─────────────────────────────────────────────────────────────────────────────
# 1. Signature Generation (Pre-sign Phase 1)
# ─────────────────────────────────────────────────────────────────────────────

def generate_cloudinary_signature(params_to_sign: dict) -> str:
    """
    Generate a HMAC-SHA256 Cloudinary upload signature.

    Cloudinary's signing algorithm (per their docs):
        1. Sort params alphabetically by key.
        2. Join as ``key=value&key=value...``
        3. Append API_SECRET.
        4. SHA-256 hash the resulting string.

    This is the canonical enterprise implementation following Cloudinary's
    official documentation for server-generated signatures.

    Args:
        params_to_sign: Dict of upload params (timestamp, folder, eager, etc.)
                        Do NOT include ``api_key``, ``file``, or ``resource_type``.

    Returns:
        Lowercase hex SHA-256 digest string.
    """
    api_secret = settings.CLOUDINARY_STORAGE.get("API_SECRET", "")
    # Sort params and build the signing string
    sorted_params = "&".join(
        f"{k}={v}"
        for k, v in sorted(params_to_sign.items())
        if v not in ("", None)
    )
    signing_string = f"{sorted_params}{api_secret}"
    return hashlib.sha256(signing_string.encode("utf-8")).hexdigest()


def generate_cloudinary_upload_params(
    user_id: str,
    asset_type: str = "avatar",
) -> CloudinaryPresignResult:
    """
    Build a complete, time-limited, signed parameter set for client-side
    direct upload to Cloudinary.

    Results are automatically cached in Redis for ``CLOUDINARY_SIGNATURE_TTL``
    seconds (default 3300s = 55 min).  Subsequent calls within the TTL window
    return the cached result instantly without re-computing the signature.

    Args:
        user_id:    UUID string of the uploading user (used to namespace the
                    Cloudinary folder).
        asset_type: One of ``avatar`` | ``product_image`` | ``product_video``
                    | ``measurement``.

    Returns:
        ``CloudinaryPresignResult`` containing all params the frontend needs to
        POST directly to Cloudinary.
    """
    from apps.common.utils.redis import cache_upload_presign, get_cached_presign

    # ── 1. Redis cache hit? ───────────────────────────────────────────────
    cached = get_cached_presign(user_id, asset_type)
    if cached:
        logger.debug("Presign cache HIT for user=%s asset=%s", user_id, asset_type)
        return CloudinaryPresignResult(**cached, success=True)

    # ── 2. Look up asset config ───────────────────────────────────────────
    config = _ASSET_CONFIGS.get(asset_type, _ASSET_CONFIGS["avatar"])
    cloud_name    = settings.CLOUDINARY_STORAGE.get("CLOUD_NAME", "")
    api_key       = settings.CLOUDINARY_STORAGE.get("API_KEY", "")
    preset_name   = getattr(settings, config["preset_setting"], "fashionistar_avatars")
    resource_type = config["resource_type"]
    folder        = f"{config['folder_prefix']}/user_{user_id}"
    eager         = config["eager"]
    timestamp     = int(time.time())

    # ── 3. Build params to sign ───────────────────────────────────────────
    # Cloudinary eager param is serialized as a pipe-separated transformation string
    eager_str = "|".join(
        ",".join(f"{k}_{v}" for k, v in t.items())
        for t in eager
    )
    params_to_sign = {
        "timestamp":      timestamp,
        "folder":         folder,
        "upload_preset":  preset_name,
        "eager":          eager_str,
        "eager_async":    "true",
    }

    # ── 4. Sign ───────────────────────────────────────────────────────────
    try:
        signature = generate_cloudinary_signature(params_to_sign)
    except Exception as exc:
        logger.error("Cloudinary signature generation failed: %s", exc)
        return CloudinaryPresignResult(
            cloud_name="", api_key="", signature="", timestamp=0,
            folder="", upload_preset="", resource_type=resource_type,
            success=False, error=str(exc),
        )

    # ── 5. Build result ───────────────────────────────────────────────────
    result = CloudinaryPresignResult(
        cloud_name=cloud_name,
        api_key=api_key,
        signature=signature,
        timestamp=timestamp,
        folder=folder,
        upload_preset=preset_name,
        resource_type=resource_type,
        eager=eager,
        eager_async=True,
        success=True,
    )

    # ── 6. Cache in Redis ─────────────────────────────────────────────────
    cache_upload_presign(user_id, asset_type, result.to_dict())

    logger.info(
        "Presign generated for user=%s asset=%s folder=%s",
        user_id, asset_type, folder,
    )
    return result


# ─────────────────────────────────────────────────────────────────────────────
# 2. Transform URL Builder — 2K / 4K / 8K Support
# ─────────────────────────────────────────────────────────────────────────────

_RES_WIDTHS = {
    "sd":  800,
    "hd":  1280,
    "fhd": 1920,
    "2k":  2560,
    "4k":  3840,
    "8k":  7680,
}


def get_cloudinary_transform_url(
    public_id:     str,
    *,
    width:         Optional[int]  = None,
    resolution:    Optional[str]  = None,   # "sd" | "hd" | "fhd" | "2k" | "4k" | "8k"
    height:        Optional[int]  = None,
    crop:          str            = "scale",
    quality:       str            = "auto",
    fetch_format:  str            = "auto",
    resource_type: str            = "image",
    secure:        bool           = True,
) -> str:
    """
    Build a Cloudinary delivery URL with transformation parameters.

    Supports 2K / 4K / 8K via the ``resolution`` shorthand.  ``quality=auto``
    and ``fetch_format=auto`` let Cloudinary select the best quality and format
    (WebP, AVIF, etc.) for each browser automatically — maximizing quality
    while minimizing bytes transferred.

    Args:
        public_id:     Cloudinary public_id of the asset.
        width:         Exact pixel width (overrides ``resolution``).
        resolution:    Shorthand: "sd" | "hd" | "fhd" | "2k" | "4k" | "8k".
        height:        Optional height.
        crop:          Cloudinary crop mode (default ``scale``).
        quality:       ``auto`` | 1–100 | cloudinary quality string.
        fetch_format:  ``auto`` | ``webp`` | ``avif`` | ``jpg`` | etc.
        resource_type: ``image`` | ``video``.
        secure:        Whether to return ``https://`` URL (always True in prod).

    Returns:
        Full delivery URL string.

    Example:
        >>> get_cloudinary_transform_url("fashionistar/products/shoe_01", resolution="4k")
        "https://res.cloudinary.com/dgpdlknc1/image/upload/f_auto,q_auto,w_3840/fashionistar/products/shoe_01"
    """
    cloud_name = settings.CLOUDINARY_STORAGE.get("CLOUD_NAME", "")
    protocol   = "https" if secure else "http"

    # Resolve width
    if width is None and resolution:
        width = _RES_WIDTHS.get(resolution.lower())

    # Build transformation string
    transforms = [
        f"f_{fetch_format}",
        f"q_{quality}",
    ]
    if width:
        transforms.append(f"w_{width}")
    if height:
        transforms.append(f"h_{height}")
    transforms.append(f"c_{crop}")

    transform_str = ",".join(transforms)
    return f"{protocol}://res.cloudinary.com/{cloud_name}/{resource_type}/upload/{transform_str}/{public_id}"


# ─────────────────────────────────────────────────────────────────────────────
# 3. Webhook Signature Validation
# ─────────────────────────────────────────────────────────────────────────────

def validate_cloudinary_webhook(
    body: bytes,
    timestamp: str,
    signature: str,
) -> bool:
    """
    Validate an incoming Cloudinary webhook notification using their
    HMAC-SHA256 signature scheme.

    Cloudinary's algorithm:
        HMAC-SHA256(body + timestamp, api_secret)

    Always validate in constant time (``hmac.compare_digest``) to prevent
    timing-attack enumeration.

    Args:
        body:      Raw request body bytes.
        timestamp: Value of the ``X-Cld-Timestamp`` header.
        signature: Value of the ``X-Cld-Signature`` header.

    Returns:
        ``True`` if signature is valid, ``False`` otherwise.
    """
    api_secret = settings.CLOUDINARY_STORAGE.get("API_SECRET", "").encode()
    data       = body + timestamp.encode()
    expected   = hmac.new(api_secret, data, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


# ─────────────────────────────────────────────────────────────────────────────
# 4. Synchronous delete (for Celery tasks)
# ─────────────────────────────────────────────────────────────────────────────

def delete_cloudinary_asset(public_id: str, resource_type: str = "image") -> Optional[dict]:
    """
    Delete an asset from Cloudinary synchronously.

    This is called from Celery worker threads — NOT from the Django request
    thread — so synchronous I/O here is completely fine.

    Returns:
        Cloudinary API response dict, or ``None`` on error.
    """
    try:
        if not public_id:
            return None
        result = cloudinary.uploader.destroy(public_id, resource_type=resource_type)
        logger.info("Cloudinary asset deleted: %s → %s", public_id, result)
        return result
    except Exception as exc:
        logger.error("Cloudinary delete failed for %s: %s", public_id, exc)
        return None


def delete_cloudinary_asset_async(public_id: str, resource_type: str = "image") -> None:
    """
    Dispatch a Celery background task to delete a Cloudinary asset.

    Uses ``transaction.on_commit`` to ensure the task fires ONLY after the
    current DB transaction commits — no risk of deleting while a rollback
    could reinstate the reference.

    Args:
        public_id:     Cloudinary public_id.
        resource_type: ``image`` | ``video`` | ``raw``.
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
                ignore_result=True,
            )
        except Exception as exc:
            logger.warning(
                "Celery broker unavailable — falling back to sync delete for %s: %s",
                public_id, exc,
            )
            delete_cloudinary_asset(public_id, resource_type)

    transaction.on_commit(_fire)


# ─────────────────────────────────────────────────────────────────────────────
# 5. Async bulk upload / delete (for batch operations, import tools, etc.)
# ─────────────────────────────────────────────────────────────────────────────

def _sync_upload_one(
    file_path:     str,
    folder:        str,
    resource_type: str,
    transformation: Optional[list],
    eager:          Optional[list],
) -> CloudinaryUploadResult:
    """Synchronous Cloudinary upload — meant to run inside ``asyncio.to_thread()``."""
    try:
        kwargs: dict = {
            "folder":          folder,
            "resource_type":   resource_type,
            "use_filename":    True,
            "unique_filename": True,
            "overwrite":       False,
            "quality":         "auto",
            "fetch_format":    "auto",
        }
        if transformation:
            kwargs["transformation"] = transformation
        if eager:
            kwargs["eager"]       = eager
            kwargs["eager_async"] = True

        res = cloudinary.uploader.upload(file_path, **kwargs)
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
        logger.error("Cloudinary upload failed [%s]: %s", file_path, exc)
        return CloudinaryUploadResult(file_path=file_path, error=str(exc), success=False)


async def async_bulk_upload_media(
    file_paths:     list[str],
    *,
    folder:         str           = "fashionistar/uploads",
    resource_type:  str           = "auto",
    transformation: Optional[list] = None,
    eager:          Optional[list] = None,
    max_concurrency: int          = 10,
) -> list[CloudinaryUploadResult]:
    """
    Upload multiple media files concurrently to Cloudinary without blocking
    the ASGI event loop.

    Enterprise design:
    - ``asyncio.Semaphore`` caps concurrent SDK calls to ``max_concurrency``
      (default 10). Cloudinary free plans allow ≈500 req/min; adjust for paid.
    - Each upload runs in ``asyncio.to_thread()`` — SDK is sync, thread pool
      keeps the event loop free.
    - ``eager_async=True`` queues server-side transformations asynchronously,
      avoiding upload-time CPU overhead.
    - Results preserve insertion order matching input ``file_paths``.

    Args:
        file_paths:      Absolute local paths or remote URLs.
        folder:          Cloudinary folder prefix.
        resource_type:   ``image`` | ``video`` | ``raw`` | ``auto``.
        transformation:  List of Cloudinary transformation dicts.
        eager:           Additional eager transformation specs.
        max_concurrency: Max simultaneous SDK calls.

    Returns:
        ``list[CloudinaryUploadResult]`` preserving input order.
    """
    sem = asyncio.Semaphore(max_concurrency)

    async def _guarded(fp: str) -> CloudinaryUploadResult:
        async with sem:
            return await asyncio.to_thread(
                _sync_upload_one, fp, folder, resource_type, transformation, eager,
            )

    tasks   = [asyncio.create_task(_guarded(fp)) for fp in file_paths]
    results = await asyncio.gather(*tasks)

    success = sum(1 for r in results if r.success)
    logger.info(
        "async_bulk_upload_media: %d/%d succeeded into '%s'",
        success, len(file_paths), folder,
    )
    return list(results)


def _sync_delete_one(public_id: str, resource_type: str) -> CloudinaryDeleteResult:
    """Synchronous Cloudinary deletion — meant to run inside ``asyncio.to_thread()``."""
    try:
        res = cloudinary.uploader.destroy(public_id, resource_type=resource_type)
        ok  = res.get("result") == "ok"
        return CloudinaryDeleteResult(
            public_id=public_id,
            resource_type=resource_type,
            result=res.get("result", ""),
            success=ok,
            error="" if ok else res.get("result", "unknown"),
        )
    except Exception as exc:
        logger.error("Cloudinary delete failed [%s]: %s", public_id, exc)
        return CloudinaryDeleteResult(
            public_id=public_id, resource_type=resource_type,
            error=str(exc), success=False,
        )


async def async_bulk_delete_media(
    public_ids:     list[str],
    *,
    resource_type:  str = "image",
    max_concurrency: int = 20,
) -> list[CloudinaryDeleteResult]:
    """
    Delete multiple Cloudinary assets concurrently without blocking the event loop.

    Automatically switches to the Cloudinary batch API (``delete_resources``)
    for sets larger than 50 assets — up to 10× faster for large clean-ups.

    Args:
        public_ids:      List of Cloudinary public_ids to delete.
        resource_type:   ``image`` | ``video`` | ``raw``.
        max_concurrency: Max simultaneous SDK calls.

    Returns:
        ``list[CloudinaryDeleteResult]`` preserving input order.
    """
    if not public_ids:
        return []

    if len(public_ids) > 50:
        # ── Batch delete path (Cloudinary batch API) ──────────────────────
        chunk_size = 100
        sem        = asyncio.Semaphore(5)  # Cloudinary rate-limit on batch calls

        async def _batch_chunk(chunk: list[str]) -> list[CloudinaryDeleteResult]:
            async with sem:
                def _sync():
                    return cloudinary.api.delete_resources(
                        chunk, resource_type=resource_type, invalidate=True,
                    )
                res     = await asyncio.to_thread(_sync)
                deleted = res.get("deleted", {})
                return [
                    CloudinaryDeleteResult(
                        public_id=pid,
                        resource_type=resource_type,
                        result=deleted.get(pid, "not found"),
                        success=deleted.get(pid) == "deleted",
                    )
                    for pid in chunk
                ]

        chunks      = [public_ids[i:i+chunk_size] for i in range(0, len(public_ids), chunk_size)]
        sub_results = await asyncio.gather(*[asyncio.create_task(_batch_chunk(c)) for c in chunks])
        results     = [item for sub in sub_results for item in sub]

    else:
        # ── Individual delete path ─────────────────────────────────────────
        sem = asyncio.Semaphore(max_concurrency)

        async def _guarded(pid: str) -> CloudinaryDeleteResult:
            async with sem:
                return await asyncio.to_thread(_sync_delete_one, pid, resource_type)

        results = list(await asyncio.gather(*[asyncio.create_task(_guarded(pid)) for pid in public_ids]))

    success = sum(1 for r in results if r.success)
    logger.info(
        "async_bulk_delete_media: %d/%d deleted (resource_type=%s)",
        success, len(public_ids), resource_type,
    )
    return results


async def async_get_media_info_bulk(
    public_ids:     list[str],
    *,
    resource_type:  str = "image",
    max_concurrency: int = 20,
) -> list[dict]:
    """
    Retrieve metadata for multiple Cloudinary assets concurrently.

    Useful for Next.js ISR / SSG pages that need width/height for
    responsive image sizing without a separate DB column.

    Returns:
        List of raw Cloudinary resource dicts (or error dicts on failure).
    """
    sem = asyncio.Semaphore(max_concurrency)

    async def _fetch(pid: str) -> dict:
        async with sem:
            def _sync():
                try:
                    return cloudinary.api.resource(pid, resource_type=resource_type)
                except Exception as exc:
                    return {"public_id": pid, "error": str(exc)}
            return await asyncio.to_thread(_sync)

    return list(await asyncio.gather(*[asyncio.create_task(_fetch(pid)) for pid in public_ids]))
