# apps/common/tasks/cloudinary.py
"""
Cloudinary background Celery tasks — Phase 4 Production Release.

Tasks
─────
  delete_cloudinary_asset_task        Background asset deletion.
  process_cloudinary_upload_webhook   Webhook → model field update (idempotent).
  generate_eager_transformations      Trigger 2K/4K/8K server-side variants.
  purge_cloudinary_cache              CDN edge-cache invalidation.
  bulk_sync_cloudinary_urls           Bulk sync multiple asset URLs to a model.

Production-Grade Features (Phase 4)
────────────────────────────────────
  ✅ Idempotency — every webhook is deduplicated via Redis + DB unique key
  ✅ Safe model resolution — ImportError / AttributeError caught gracefully
  ✅ Audit trail — AuditService.log() called on avatar / product saves
  ✅ Asset type differentiation — image → "image", video → "video_url"
  ✅ Race-condition safety — IntegrityError on duplicate mark_processed() is a no-op
  ✅ Eager transform chaining — product images trigger 2K/4K generation automatically
  ✅ Atomic transactions — each DB update in transaction.atomic()
"""

from __future__ import annotations

import logging
import time
import uuid as _uuid
from typing import Optional

from celery import shared_task
from django.db import IntegrityError, transaction

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# CONSTANTS
# ═══════════════════════════════════════════════════════════════════════════

# Map Cloudinary resource_type → target model field name
RESOURCE_TYPE_FIELD_MAP: dict[str, str] = {
    "image": "image",
    "video": "video_url",
    "raw":   "file_url",
}

# Asset types that should trigger eager transform chaining after a webhook
EAGER_TRANSFORM_ASSET_TYPES = {
    "product_image",
    "product_gallery",
    "product_video",
    "avatar",
    "measurement",
    "collection",
    "blog",
}

# Audit event types (must match AuditEventLog EventType choices)
_EVENT_AVATAR_CLOUDINARY   = "avatar_cloudinary_hook"
_EVENT_WEBHOOK_RECEIVED    = "webhook_received"
_EVENT_VENDOR_AVATAR       = "vendor_avatar_uploaded"
_EVENT_PRODUCT_IMAGE       = "product_image_uploaded"
_EVENT_VENDOR_PRODUCT_IMG  = "vendor_product_image"
_EVENT_VENDOR_PRODUCT_VID  = "vendor_product_video"
_EVENT_ADMIN_CATEGORY      = "admin_category_image"
_EVENT_ADMIN_COLLECTION    = "admin_collection_image"
_EVENT_VENDOR_BULK_UPLOAD  = "vendor_bulk_upload"


# ═══════════════════════════════════════════════════════════════════════════
# MODEL RESOLVER — safe, production-grade
# ═══════════════════════════════════════════════════════════════════════════

def _resolve_model(dotted_path: str):
    """
    Dynamically import a model from its dotted path.
    
    Raises ImportError or AttributeError if the module/model doesn't exist.
    Call _safe_resolve_model() for a fault-tolerant version.
    """
    parts = dotted_path.rsplit(".", 1)
    if len(parts) != 2:
        raise ImportError(f"Invalid dotted model path: {dotted_path!r}")
    module = __import__(parts[0], fromlist=[parts[1]])
    return getattr(module, parts[1])


def _safe_resolve_model(dotted_path: str):
    """
    Safely import a model from its dotted path.
    
    Returns None if the app/model doesn't exist yet — prevents webhook
    task crashes when routes reference future apps like store, vendor, etc.
    
    This is critical for production stability: not all apps are implemented
    yet (store, vendor, admin_backend, Blog, measurements) but their routes
    are pre-configured so zero code changes are needed when those apps land.
    
    Args:
        dotted_path: Dotted model import path, e.g. "store.models.Product"
    
    Returns:
        Model class, or None if not yet implemented.
    """
    try:
        return _resolve_model(dotted_path)
    except (ImportError, AttributeError, ModuleNotFoundError) as exc:
        logger.warning(
            "Model not yet implemented — route skipped: %s — %s",
            dotted_path, exc,
        )
        return None


# ═══════════════════════════════════════════════════════════════════════════
# PK EXTRACTORS
# ═══════════════════════════════════════════════════════════════════════════

def _extract_user_uuid(parts: list[str]) -> Optional[str]:
    """Extract user UUID from a path like /avatars/user_{uuid}/filename."""
    seg = next((p for p in parts if p.startswith("user_")), None)
    if not seg:
        return None
    raw = seg.removeprefix("user_")
    try:
        return str(_uuid.UUID(raw))
    except ValueError:
        return None


def _extract_short_id(parts: list[str]) -> Optional[str]:
    """Extract the second-to-last path segment as the PK."""
    return parts[-2] if len(parts) >= 2 else None


# ═══════════════════════════════════════════════════════════════════════════
# WEBHOOK ROUTING TABLE
# ═══════════════════════════════════════════════════════════════════════════
# Each entry: (path_substring, dotted_model_path, pk_field, pk_extractor, asset_label)
#
# IMPORTANT: Only "apps.authentication.models.UnifiedUser" routes are LIVE.
# All other routes reference apps not yet implemented. They are pre-wired so
# no code changes are needed when those apps go live.
# _safe_resolve_model() ensures they fail gracefully until then.

_WEBHOOK_ROUTES: list[tuple[str, str, str, callable, str]] = [
    # (path_substr, model_dotted, pk_field, pk_getter, asset_label_for_audit)
    (
        "/avatars/user_",
        "apps.authentication.models.UnifiedUser",
        "id",
        _extract_user_uuid,
        "avatar",                     # ← LIVE (authentication app exists)
    ),
    (
        "/products/images/",
        "store.models.Product",
        "pid",
        _extract_short_id,
        "product_image",              # ← FUTURE (store app)
    ),
    (
        "/products/gallery/",
        "store.models.Gallery",
        "gid",
        _extract_short_id,
        "product_gallery",            # ← FUTURE (store app)
    ),
    (
        "/products/videos/",
        "store.models.Product",
        "pid",
        _extract_short_id,
        "product_video",              # ← FUTURE (store app)
    ),
    (
        "/products/colors/",
        "store.models.Color",
        "id",
        _extract_short_id,
        "product_color",              # ← FUTURE (store app)
    ),
    (
        "/vendors/images/",
        "vendor.models.Vendor",
        "vid",
        _extract_short_id,
        "vendor_shop",                # ← FUTURE (vendor app)
    ),
    (
        "/categories/images/",
        "admin_backend.models.category.Category",
        "id",
        _extract_short_id,
        "category",                   # ← FUTURE (admin_backend app)
    ),
    (
        "/brands/images/",
        "admin_backend.models.brand.Brand",
        "id",
        _extract_short_id,
        "brand",                      # ← FUTURE (admin_backend app)
    ),
    (
        "/collections/images/",
        "admin_backend.models.collection.Collections",
        "id",
        _extract_short_id,
        "collection",                 # ← FUTURE (admin_backend app)
    ),
    (
        "/profiles/images/",
        "userauths.models.Profile",
        "id",
        _extract_short_id,
        "profile",                    # ← LEGACY (userauths app)
    ),
    (
        "/blogs/images/",
        "Blog.models.Blog",
        "id",
        _extract_short_id,
        "blog",                       # ← FUTURE (Blog app)
    ),
    (
        "/measurements/",
        "measurements.models.Measurements",
        "id",
        _extract_short_id,
        "measurement",                # ← FUTURE (measurements app)
    ),
    (
        "/chat/files/",
        "chat.models.Message",
        "id",
        _extract_short_id,
        "chat_file",                  # ← FUTURE (chat app)
    ),
]


def _get_target_field(path_substr: str, resource_type: str, asset_label: str) -> str:
    """
    Determine the model field name based on path prefix and resource type.
    
    Avatar always maps to "avatar" regardless of resource_type.
    Video assets map to "video_url" when the path indicates a video.
    Everything else follows the RESOURCE_TYPE_FIELD_MAP.
    """
    if "/avatars/" in path_substr:
        return "avatar"
    if "/products/videos/" in path_substr or resource_type == "video":
        return "video_url"
    if resource_type == "raw":
        return "file_url"
    return "image"


def _get_audit_event_type(asset_label: str, resource_type: str) -> str:
    """Map asset_label + resource_type to the correct audit event type string."""
    mapping = {
        "avatar":        _EVENT_AVATAR_CLOUDINARY,
        "product_image": _EVENT_PRODUCT_IMAGE,
        "product_video": _EVENT_VENDOR_PRODUCT_VID,
        "product_gallery": _EVENT_PRODUCT_IMAGE,
        "category":      _EVENT_ADMIN_CATEGORY,
        "collection":    _EVENT_ADMIN_COLLECTION,
    }
    return mapping.get(asset_label, _EVENT_WEBHOOK_RECEIVED)


def _dispatch_audit_log(
    asset_label: str,
    event_type: str,
    model_path: str,
    pk_value: str,
    secure_url: str,
    public_id: str,
) -> None:
    """Fire-and-forget audit log dispatch. Never raises."""
    try:
        from apps.audit_logs.services.audit import AuditService
        AuditService.log(
            event_type=event_type,
            action=f"Cloudinary {asset_label} webhook processed",
            resource_type=model_path.rsplit(".", 1)[-1],
            resource_id=pk_value,
            new_values={"secure_url": secure_url[:120] if secure_url else ""},
            metadata={
                "public_id": public_id,
                "asset_label": asset_label,
                "cloudinary_webhook": True,
            },
        )
    except Exception as exc:
        logger.warning("Audit log dispatch failed (non-fatal): %s", exc)


# ═══════════════════════════════════════════════════════════════════════════
# 1. SINGLE ASSET DELETION
# ═══════════════════════════════════════════════════════════════════════════

@shared_task(
    name="delete_cloudinary_asset_task",
    bind=True,
    max_retries=3,
    default_retry_delay=30,
    ignore_result=True,
)
def delete_cloudinary_asset_task(
    self,
    public_id: str,
    resource_type: str = "image",
):
    """
    Delete an asset from Cloudinary in the background.
    Dispatched from model delete() hooks to avoid blocking requests.
    """
    from apps.common.utils import delete_cloudinary_asset

    try:
        result = delete_cloudinary_asset(public_id, resource_type=resource_type)
        if result and result.get("result") == "ok":
            logger.info("Background Cloudinary deletion succeeded: %s", public_id)
        else:
            logger.warning(
                "Background Cloudinary deletion unexpected for %s: %s",
                public_id, result,
            )
    except Exception as exc:
        logger.error("Failed to delete Cloudinary asset %s: %s", public_id, exc)
        raise self.retry(exc=exc)


# ═══════════════════════════════════════════════════════════════════════════
# 2. WEBHOOK PROCESSING — Phase 4 Production Implementation
# ═══════════════════════════════════════════════════════════════════════════

@shared_task(
    name="process_cloudinary_upload_webhook",
    bind=True,
    max_retries=3,
    default_retry_delay=10,
    ignore_result=True,
)
def process_cloudinary_upload_webhook(self, payload: dict) -> None:
    """
    Process a validated Cloudinary webhook notification and persist the
    secure_url to the correct model field.

    Production Design Principles
    ────────────────────────────
    ① IDEMPOTENCY: SHA-256 key checked in Redis + DB. Duplicate webhooks
       (Cloudinary retries on network failure) are silently discarded.
    ② SAFE ROUTING: Non-existent app models resolve to None — zero crashes.
    ③ AUDIT TRAIL: mark_processed() writes to CloudinaryProcessedWebhook.
    ④ AUDIT EVENTS: AuditService.log() called for avatar and product saves.
    ⑤ EAGER CHAINING: product/avatar images trigger 2K/4K variant generation.
    ⑥ ATOMIC TRANSACTIONS: each DB update in transaction.atomic().
    ⑦ RACE SAFETY: IntegrityError on duplicate mark_processed() is a no-op.
    ⑧ VIDEO AWARE: resource_type=video routes to "video_url" field, not "image".

    Called ONLY after HMAC-SHA1 signature validation in CloudinaryWebhookView.
    """
    from apps.common.utils.webhook_idempotency import (
        generate_idempotency_key,
        is_duplicate,
        mark_processed,
    )

    public_id     = payload.get("public_id", "")
    secure_url    = payload.get("secure_url", "")
    resource_type = payload.get("resource_type", "image")      # "image" | "video" | "raw"
    created_at    = str(payload.get("created_at", ""))
    notification_type = payload.get("notification_type", "upload")

    if not public_id or not secure_url:
        logger.warning(
            "process_cloudinary_upload_webhook: missing public_id or secure_url — "
            "notification_type=%s", notification_type,
        )
        return

    # ── ① IDEMPOTENCY CHECK ──────────────────────────────────────────────
    idem_key = generate_idempotency_key(public_id, created_at, resource_type)
    if is_duplicate(idem_key, check_database=True):
        logger.info(
            "Duplicate Cloudinary webhook skipped: key=%s public_id=%s",
            idem_key[:16], public_id[:60],
        )
        return

    t_start        = time.monotonic()
    model_target   = "unknown"
    pk_value       = None
    asset_label_out = "unknown"
    routed         = False

    parts = public_id.split("/")

    try:
        # ── ② ROUTE MATCHING ─────────────────────────────────────────────
        for path_substr, model_dotted, pk_field, pk_getter, asset_label in _WEBHOOK_ROUTES:
            if path_substr not in public_id:
                continue

            # ── ③ SAFE MODEL RESOLUTION ──────────────────────────────────
            Model = _safe_resolve_model(model_dotted)
            if Model is None:
                logger.info(
                    "Cloudinary webhook: route '%s' matched but model %s not yet "
                    "implemented — skipping (will auto-activate when app is added).",
                    path_substr, model_dotted,
                )
                # Mark as "processed" so we don't retry forever for a missing model
                processing_ms = (time.monotonic() - t_start) * 1000
                _safe_mark_processed(
                    idem_key, public_id, resource_type,
                    f"future:{model_dotted}", None, None,
                    processing_ms, success=True, error_message=None,
                )
                return

            # ── ④ PK EXTRACTION ──────────────────────────────────────────
            pk_value = pk_getter(parts)
            if not pk_value:
                logger.warning(
                    "Cloudinary webhook: cannot extract PK from public_id=%s "
                    "for route %s — skipping.",
                    public_id, path_substr,
                )
                return

            # ── ⑤ DETERMINE TARGET FIELD ─────────────────────────────────
            target_field = _get_target_field(path_substr, resource_type, asset_label)
            model_target  = asset_label
            asset_label_out = asset_label

            # ── ⑥ ATOMIC DB UPDATE ────────────────────────────────────────
            with transaction.atomic():
                updated = Model.objects.filter(
                    **{pk_field: pk_value}
                ).update(**{target_field: secure_url})

            if updated:
                logger.info(
                    "✅ Cloudinary webhook: saved %s.%s for %s=%s | url=%s...",
                    model_dotted.rsplit(".", 1)[-1],
                    target_field,
                    pk_field,
                    pk_value,
                    secure_url[:60],
                )
            else:
                logger.warning(
                    "⚠️ Cloudinary webhook: no %s row found for %s=%s (public_id=%s)",
                    model_dotted, pk_field, pk_value, public_id,
                )

            routed = True
            break

        if not routed:
            logger.info(
                "Cloudinary webhook: no route matched for public_id=%s — "
                "secure_url=%s (generic/unmapped asset)",
                public_id, secure_url[:60],
            )

        # ── ⑦ MARK PROCESSED (Redis + DB audit trail) ────────────────────
        processing_ms = (time.monotonic() - t_start) * 1000
        _safe_mark_processed(
            idem_key,
            public_id,
            resource_type,
            model_target,
            str(pk_value) if pk_value else None,
            secure_url,
            processing_ms,
            success=True,
            error_message=None,
        )

        # ── ⑧ AUDIT LOG ──────────────────────────────────────────────────
        if routed and pk_value:
            event_type = _get_audit_event_type(asset_label_out, resource_type)
            _dispatch_audit_log(
                asset_label_out,
                event_type,
                model_target,
                str(pk_value),
                secure_url,
                public_id,
            )

        # ── ⑨ EAGER TRANSFORM CHAINING ───────────────────────────────────
        # Trigger 2K/4K/8K server-side variants for images/videos
        # after a small delay to let Cloudinary settle.
        if routed and asset_label_out in EAGER_TRANSFORM_ASSET_TYPES:
            generate_eager_transformations.apply_async(
                kwargs={
                    "public_id": public_id,
                    "asset_type": asset_label_out,
                },
                countdown=5,    # 5s delay: let Cloudinary complete the primary upload
                ignore_result=True,
            )
            logger.debug(
                "Eager transforms scheduled for public_id=%s asset_type=%s",
                public_id, asset_label_out,
            )

    except Exception as exc:
        # ── FAILURE PATH: mark_processed(success=False) + retry ──────────
        processing_ms = (time.monotonic() - t_start) * 1000
        logger.exception(
            "❌ process_cloudinary_upload_webhook FAILED for public_id=%s: %s",
            public_id, exc,
        )
        _safe_mark_processed(
            idem_key,
            public_id,
            resource_type,
            model_target,
            str(pk_value) if pk_value else None,
            None,
            processing_ms,
            success=False,
            error_message=str(exc)[:500],
        )
        raise self.retry(exc=exc)


def _safe_mark_processed(
    idem_key: str,
    public_id: str,
    resource_type: str,
    model_target: str,
    model_pk: Optional[str],
    secure_url: Optional[str],
    processing_time_ms: float,
    success: bool,
    error_message: Optional[str],
) -> None:
    """
    Wrapper around mark_processed() that catches IntegrityError.
    
    IntegrityError occurs when two Celery workers race to process the same
    webhook simultaneously — the second worker tries to INSERT a duplicate
    idempotency_key. This is a no-op (first write already won).
    """
    try:
        from apps.common.utils.webhook_idempotency import mark_processed
        mark_processed(
            idempotency_key=idem_key,
            public_id=public_id,
            asset_type=resource_type,
            model_target=model_target,
            model_pk=model_pk,
            secure_url=secure_url,
            processing_time_ms=processing_time_ms,
            success=success,
            error_message=error_message,
        )
    except IntegrityError:
        logger.debug(
            "mark_processed IntegrityError (concurrent duplicate) — safe to ignore: %s",
            idem_key[:16],
        )
    except Exception as exc:
        logger.warning("mark_processed failed (non-fatal): %s", exc)


# ═══════════════════════════════════════════════════════════════════════════
# 3. EAGER TRANSFORMATIONS (2K / 4K / 8K variants)
# ═══════════════════════════════════════════════════════════════════════════

@shared_task(
    name="generate_eager_transformations",
    bind=True,
    max_retries=2,
    default_retry_delay=30,
    ignore_result=True,
)
def generate_eager_transformations(
    self,
    public_id: str,
    asset_type: str = "product_image",
) -> None:
    """
    Trigger (or re-trigger) server-side eager transformations on a
    Cloudinary asset. Generates 2K/4K/8K variants + WebP/AVIF derivatives.

    Non-blocking: uses eager_async=True so Cloudinary processes variants
    in the background and calls our webhook when complete.

    Used for:
      - Product images: 1200px, 800px, 400px, 3840px (4K)
      - User avatars: 400px, 150px face crop
      - Collection heroes: 2560px, 1920px, 800px, 400px
    """
    import cloudinary.uploader
    from apps.common.utils.cloudinary import _ASSET_CONFIGS

    config = _ASSET_CONFIGS.get(asset_type, _ASSET_CONFIGS["generic_image"])
    eager  = config.get("eager", [])

    if not eager:
        logger.debug(
            "generate_eager_transformations: no eager config for asset_type=%s — skipping",
            asset_type,
        )
        return

    try:
        cloudinary.uploader.explicit(
            public_id,
            type="upload",
            eager=eager,
            eager_async=True,   # Non-blocking: Cloudinary calls webhook when done
        )
        logger.info(
            "generate_eager_transformations: triggered %d transforms for %s (asset=%s)",
            len(eager), public_id[:60], asset_type,
        )
    except Exception as exc:
        logger.error(
            "generate_eager_transformations FAILED for public_id=%s: %s",
            public_id, exc,
        )
        raise self.retry(exc=exc)


# ═══════════════════════════════════════════════════════════════════════════
# 4. CDN CACHE INVALIDATION
# ═══════════════════════════════════════════════════════════════════════════

@shared_task(
    name="purge_cloudinary_cache",
    bind=True,
    max_retries=2,
    default_retry_delay=15,
    ignore_result=True,
)
def purge_cloudinary_cache(
    self,
    public_ids: list,
    resource_type: str = "image",
) -> None:
    """
    Trigger Cloudinary CDN edge cache invalidation.

    Call when a user replaces an avatar or product image so the old
    CDN-cached asset is flushed within seconds across all PoPs.

    Args:
        public_ids:    List of Cloudinary public_ids to invalidate.
        resource_type: "image" | "video" | "raw".
    """
    import cloudinary.api

    try:
        if not public_ids:
            return
        result = cloudinary.api.delete_resources(
            public_ids,
            resource_type=resource_type,
            invalidate=True,     # CDN edge flush
            keep_original=True,  # Keep the file; just bust the cache
        )
        logger.info(
            "purge_cloudinary_cache: CDN invalidated %d assets: %s",
            len(public_ids), result,
        )
    except Exception as exc:
        logger.error(
            "purge_cloudinary_cache FAILED for %s: %s", public_ids, exc,
        )
        raise self.retry(exc=exc)


# ═══════════════════════════════════════════════════════════════════════════
# 5. BULK SYNC — Write many Cloudinary URLs to a model in one atomic pass
# ═══════════════════════════════════════════════════════════════════════════

@shared_task(
    name="bulk_sync_cloudinary_urls",
    bind=True,
    max_retries=2,
    default_retry_delay=20,
    ignore_result=True,
)
def bulk_sync_cloudinary_urls(
    self,
    model_path: str,
    pk_field: str,
    image_field: str,
    updates: list[dict],
) -> None:
    """
    Bulk-update Cloudinary URLs for multiple model instances in one atomic pass.

    Production Design
    ─────────────────
    ✅ All updates wrapped in transaction.atomic() — all-or-nothing
    ✅ Idempotent: safe to retry on Celery failure
    ✅ Audit log dispatched for bulk operations
    ✅ Safe model resolution — won't crash if store app not yet deployed

    Args:
        model_path  : Dotted path, e.g. "store.models.Gallery".
        pk_field    : PK or unique field name, e.g. "gid".
        image_field : Target URL field name, e.g. "image".
        updates     : List of {"pk": ..., "url": ...} dicts.

    Example:
        bulk_sync_cloudinary_urls.apply_async(kwargs={
            "model_path": "store.models.Gallery",
            "pk_field": "gid",
            "image_field": "image",
            "updates": [
                {"pk": "abc", "url": "https://res.cloudinary.com/..."},
                {"pk": "def", "url": "https://res.cloudinary.com/..."},
            ]
        })
    """
    if not updates:
        return

    Model = _safe_resolve_model(model_path)
    if Model is None:
        logger.warning(
            "bulk_sync_cloudinary_urls: model %s not yet implemented — skipping %d items",
            model_path, len(updates),
        )
        return

    try:
        success_count = 0
        fail_count    = 0

        with transaction.atomic():
            for item in updates:
                pk_val  = item.get("pk")
                url_val = item.get("url")

                if not pk_val or not url_val:
                    logger.warning(
                        "bulk_sync_cloudinary_urls: skipping invalid item %s", item
                    )
                    fail_count += 1
                    continue

                updated = Model.objects.filter(
                    **{pk_field: pk_val}
                ).update(**{image_field: url_val})

                if updated:
                    success_count += 1
                else:
                    logger.warning(
                        "bulk_sync_cloudinary_urls: no row found %s=%s in %s",
                        pk_field, pk_val, model_path,
                    )
                    fail_count += 1

        logger.info(
            "bulk_sync_cloudinary_urls: %s — %d updated, %d failed",
            model_path, success_count, fail_count,
        )

        # Audit log for bulk vendor upload
        try:
            from apps.audit_logs.services.audit import AuditService
            AuditService.log(
                event_type=_EVENT_VENDOR_BULK_UPLOAD,
                action=f"Bulk Cloudinary URL sync: {model_path} — {success_count} updated",
                resource_type=model_path.rsplit(".", 1)[-1],
                metadata={
                    "model_path": model_path,
                    "pk_field": pk_field,
                    "image_field": image_field,
                    "total_updates": len(updates),
                    "success_count": success_count,
                    "fail_count": fail_count,
                },
            )
        except Exception as exc:
            logger.debug("Audit log for bulk sync failed (non-fatal): %s", exc)

    except Exception as exc:
        logger.exception(
            "bulk_sync_cloudinary_urls FAILED for %s: %s", model_path, exc,
        )
        raise self.retry(exc=exc)
