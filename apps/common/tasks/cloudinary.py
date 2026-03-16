# apps/common/tasks/cloudinary.py
"""
Cloudinary background Celery tasks.

Tasks:
    delete_cloudinary_asset_task      — Background Cloudinary asset deletion.
    process_cloudinary_upload_webhook — Webhook payload → model field update.
    generate_eager_transformations    — Trigger 2K/4K/8K server-side variants.
    purge_cloudinary_cache            — CDN edge cache invalidation.
    bulk_sync_cloudinary_urls         — Bulk sync multiple asset URLs to a model.
"""

from __future__ import annotations

import logging
import uuid as _uuid

from celery import shared_task
from django.db import transaction

logger = logging.getLogger(__name__)


# ================================================================
# 1. SINGLE ASSET DELETION
# ================================================================

@shared_task(
    name="delete_cloudinary_asset_task",
    bind=True,
    max_retries=3,
    default_retry_delay=30,
    ignore_result=True,
)
def delete_cloudinary_asset_task(self, public_id: str, resource_type: str = "image"):
    """
    Delete an asset from Cloudinary in the background.
    Dispatched from model `delete()` hooks to avoid blocking requests.
    """
    from apps.common.utils import delete_cloudinary_asset

    try:
        result = delete_cloudinary_asset(public_id, resource_type=resource_type)
        if result and result.get("result") == "ok":
            logger.info(
                "Background Cloudinary deletion succeeded: public_id=%s", public_id
            )
        else:
            logger.warning(
                "Background Cloudinary deletion returned unexpected result for %s: %s",
                public_id, result,
            )
    except Exception as exc:
        logger.error("Failed to delete Cloudinary asset %s: %s", public_id, exc)
        raise self.retry(exc=exc)


# ================================================================
# 2. WEBHOOK PROCESSING — Route payload to correct model field
# ================================================================

# Routing table: public_id folder substring → (model_import, field_name, pk_extractor)
# pk_extractor: function that takes public_id parts list and returns the PK string.

def _extract_user_uuid(parts: list[str]):
    seg = next((p for p in parts if p.startswith("user_")), None)
    if not seg:
        return None
    try:
        return str(_uuid.UUID(seg.removeprefix("user_")))
    except ValueError:
        return None


def _extract_short_id(parts: list[str], prefix_len: int = 2):
    """Extract an arbitrary short ID from the second-to-last path component."""
    return parts[-2] if len(parts) >= 2 else None


# Maps a unique path substring to (app.Model, field, pk_getter)
_WEBHOOK_ROUTES: list[tuple[str, str, str, callable]] = [
    # (path_substring, app.Model dotted path, pk_field, pk_getter)
    ("/avatars/user_",          "apps.authentication.models.UnifiedUser",  "id",     _extract_user_uuid),
    ("/products/images/",       "store.models.Product",                    "pid",    lambda p: _extract_short_id(p, 12)),
    ("/products/gallery/",      "store.models.Gallery",                    "gid",    lambda p: _extract_short_id(p, 10)),
    ("/products/colors/",       "store.models.Color",                      "id",     lambda p: _extract_short_id(p, 2)),
    ("/vendors/images/",        "vendor.models.Vendor",                    "vid",    lambda p: _extract_short_id(p, 10)),
    ("/categories/images/",     "admin_backend.models.category.Category",  "id",     lambda p: _extract_short_id(p, 10)),
    ("/brands/images/",         "admin_backend.models.brand.Brand",        "id",     lambda p: _extract_short_id(p, 10)),
    ("/collections/images/",    "admin_backend.models.collection.Collections", "id", lambda p: _extract_short_id(p, 10)),
    ("/profiles/images/",       "userauths.models.Profile",                "id",     lambda p: _extract_short_id(p, 10)),
    ("/blogs/images/",          "Blog.models.Blog",                        "id",     lambda p: _extract_short_id(p, 10)),
    ("/measurements/",          "measurements.models.Measurements",        "id",     lambda p: _extract_short_id(p, 10)),
]


def _resolve_model(dotted_path: str):
    """Dynamically import a model from its dotted path."""
    parts = dotted_path.rsplit(".", 1)
    if len(parts) != 2:
        raise ImportError(f"Invalid dotted model path: {dotted_path!r}")
    module = __import__(parts[0], fromlist=[parts[1]])
    return getattr(module, parts[1])


@shared_task(
    name="process_cloudinary_upload_webhook",
    bind=True,
    max_retries=3,
    default_retry_delay=10,
    ignore_result=True,
)
def process_cloudinary_upload_webhook(self, payload: dict):
    """
    Process a validated Cloudinary webhook notification and persist the
    ``secure_url`` to the correct model field.

    Called ONLY after HMAC-SHA256 signature validation in the webhook view.

    Routing: folder prefix of ``public_id`` → model → field update.
    Idempotent: uses ``filter().update()`` which is a no-op if pk not found.
    Atomic: each update is wrapped in ``transaction.atomic()``.
    """
    public_id  = payload.get("public_id", "")
    secure_url = payload.get("secure_url", "")
    asset_field = payload.get("asset_field", "image")  # default field name

    if not public_id or not secure_url:
        logger.warning(
            "process_cloudinary_upload_webhook: empty public_id or secure_url"
        )
        return

    parts = public_id.split("/")
    routed = False

    try:
        for path_substr, model_path, pk_field, pk_getter in _WEBHOOK_ROUTES:
            if path_substr in public_id:
                pk_value = pk_getter(parts)
                if not pk_value:
                    logger.warning(
                        "process_cloudinary_upload_webhook: cannot extract PK "
                        "from public_id=%s for model=%s",
                        public_id, model_path,
                    )
                    return

                Model = _resolve_model(model_path)

                # avatar uses URLField → target field is "avatar"
                if path_substr == "/avatars/user_":
                    target_field = "avatar"
                else:
                    target_field = asset_field  # supplied by presign or default "image"

                with transaction.atomic():
                    updated = Model.objects.filter(
                        **{pk_field: pk_value}
                    ).update(**{target_field: secure_url})

                if updated:
                    logger.info(
                        "Cloudinary webhook: saved %s.%s=%s for %s=%s",
                        model_path, target_field,
                        secure_url[:60], pk_field, pk_value,
                    )
                else:
                    logger.warning(
                        "Cloudinary webhook: no %s row found for %s=%s (public_id=%s)",
                        model_path, pk_field, pk_value, public_id,
                    )
                routed = True
                break

        if not routed:
            logger.info(
                "Cloudinary webhook: unrouted public_id=%s — "
                "no model updated. secure_url=%s",
                public_id, secure_url[:60],
            )

    except Exception as exc:
        logger.exception(
            "process_cloudinary_upload_webhook FAILED for public_id=%s: %s",
            public_id, exc,
        )
        raise self.retry(exc=exc)


# ================================================================
# 3. EAGER TRANSFORMATIONS (2K / 4K / 8K variants)
# ================================================================

@shared_task(
    name="generate_eager_transformations",
    bind=True,
    max_retries=2,
    default_retry_delay=30,
    ignore_result=True,
)
def generate_eager_transformations(self, public_id: str, asset_type: str = "product_image"):
    """
    Trigger (or re-trigger) eager server-side image transformations on an
    existing Cloudinary asset.

    Used to generate 2K / 4K / 8K responsive variants and WebP/AVIF
    derivatives for Next.js ``<Image>`` optimization.
    """
    import cloudinary.uploader
    from apps.common.utils.cloudinary import _ASSET_CONFIGS

    config = _ASSET_CONFIGS.get(asset_type, _ASSET_CONFIGS["product_image"])
    eager  = config.get("eager", [])

    try:
        cloudinary.uploader.explicit(
            public_id,
            type="upload",
            eager=eager,
            eager_async=True,
        )
        logger.info(
            "generate_eager_transformations: triggered for public_id=%s asset=%s",
            public_id, asset_type,
        )
    except Exception as exc:
        logger.error(
            "generate_eager_transformations FAILED for public_id=%s: %s",
            public_id, exc,
        )
        raise self.retry(exc=exc)


# ================================================================
# 4. CDN CACHE INVALIDATION
# ================================================================

@shared_task(
    name="purge_cloudinary_cache",
    bind=True,
    max_retries=2,
    default_retry_delay=15,
    ignore_result=True,
)
def purge_cloudinary_cache(self, public_ids: list, resource_type: str = "image"):
    """
    Trigger Cloudinary CDN edge cache invalidation.

    Call this when a user replaces an avatar or product image so the
    old CDN-cached asset is flushed within seconds.

    Args:
        public_ids:    List of Cloudinary public_ids to invalidate.
        resource_type: ``image`` | ``video`` | ``raw``.
    """
    import cloudinary.api

    try:
        if not public_ids:
            return
        result = cloudinary.api.delete_resources(
            public_ids,
            resource_type=resource_type,
            invalidate=True,     # CDN edge purge
            keep_original=True,  # do NOT delete file, just invalidate cache
        )
        logger.info(
            "purge_cloudinary_cache: CDN invalidated for %d assets: %s",
            len(public_ids), result,
        )
    except Exception as exc:
        logger.error(
            "purge_cloudinary_cache FAILED for public_ids=%s: %s",
            public_ids, exc,
        )
        raise self.retry(exc=exc)


# ================================================================
# 5. BULK SYNC — Write many Cloudinary URLs to a model in one pass
# ================================================================

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
):
    """
    Bulk-update Cloudinary URLs for multiple model instances.

    Use for product galleries (3-5 images per product) or any
    bulk import workflow.

    Runs each update in a single ``atomic()`` block for consistency.
    Idempotent — safe to retry.

    Args:
        model_path (str):  Dotted import path, e.g. ``"store.models.Gallery"``.
        pk_field (str):    PK or unique field name, e.g. ``"gid"``.
        image_field (str): Target URL field name, e.g. ``"image"``.
        updates (list):    List of ``{"pk": ..., "url": ...}`` dicts.

    Example payload:
        {
            "model_path": "store.models.Gallery",
            "pk_field": "gid",
            "image_field": "image",
            "updates": [
                {"pk": "abc123", "url": "https://res.cloudinary.com/..."},
                {"pk": "def456", "url": "https://res.cloudinary.com/..."},
            ]
        }
    """
    if not updates:
        return

    try:
        Model = _resolve_model(model_path)
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
                        "bulk_sync_cloudinary_urls: no %s row found for %s=%s",
                        model_path, pk_field, pk_val,
                    )
                    fail_count += 1

        logger.info(
            "bulk_sync_cloudinary_urls: %s — %d updated, %d failed",
            model_path, success_count, fail_count,
        )

    except Exception as exc:
        logger.exception(
            "bulk_sync_cloudinary_urls FAILED for %s: %s", model_path, exc
        )
        raise self.retry(exc=exc)
