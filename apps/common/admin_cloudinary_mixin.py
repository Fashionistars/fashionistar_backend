# apps/common/admin_cloudinary_mixin.py
"""
Cloudinary Admin Upload Mixin -- Phase 6 Production.

Provides CloudinaryUploadAdminMixin for Django ModelAdmin classes that have
image/video fields stored as Cloudinary URLs.

When an admin user uploads a file via the Django admin panel (e.g., Category
image, Brand logo, Collection banner), the mixin:

  SYNC MODE (default, ``CLOUDINARY_ADMIN_ASYNC = False``):
    1. Uploads directly to Cloudinary (blocking the admin save)
    2. Writes the returned secure_url to the model
    3. Logs an ADMIN_ACTION audit event

  ASYNC MODE (``CLOUDINARY_ADMIN_ASYNC = True`` in settings):
    1. Reads and base64-encodes the uploaded file bytes
    2. Saves the model WITHOUT the Cloudinary URL (field remains empty initially)
    3. Dispatches ``process_admin_cloudinary_upload.apply_async()`` to Celery
    4. Admin save returns immediately (<200ms, no Cloudinary HTTP round-trip)
    5. Celery worker uploads, writes the URL, and fires the audit log

  The async path uses ``acks_late=True`` + ``max_retries=3`` on the Celery task
  to guarantee at-least-once delivery even if the worker dies mid-upload.

Usage
-----
    from apps.common.admin_cloudinary_mixin import CloudinaryUploadAdminMixin

    @admin.register(Category)
    class CategoryAdmin(CloudinaryUploadAdminMixin, ModelAdmin):
        cloudinary_fields = {
            "image": ("fashionistar/categories/images", "category"),
            "banner": ("fashionistar/categories/banners", "generic_image"),
        }

cloudinary_fields Format
------------------------
    {
        "<django_field_name>": ("<cloudinary_folder>", "<asset_type_key>"),
    }

Where asset_type_key is any key from _ASSET_CONFIGS in utils/cloudinary.py
(e.g. "avatar", "product_image", "category", "collection", "brand", etc.)

Settings
--------
    CLOUDINARY_ADMIN_ASYNC = True   # Enable async Celery path (production)
    CLOUDINARY_ADMIN_ASYNC = False  # Sync inline path (dev default)
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class CloudinaryUploadAdminMixin:
    """
    Django ModelAdmin mixin for Cloudinary image/video uploads via the admin panel.

    Overrides save_model() to intercept file uploads, push them to Cloudinary,
    and store only the secure_url on the model. No local file storage is used.

    Attributes
    ──────────
    cloudinary_fields : dict
        Maps model field names to (cloudinary_folder, asset_type) tuples.
        Example:
            cloudinary_fields = {
                "image":  ("fashionistar/categories/images", "category"),
                "banner": ("fashionistar/categories/banners", "generic_image"),
            }
    """

    # Subclasses declare their Cloudinary fields here.
    cloudinary_fields: dict[str, tuple[str, str]] = {}

    def save_model(
        self,
        request: Any,
        obj: Any,
        form: Any,
        change: bool,
    ) -> None:
        """
        Intercept admin save to upload files to Cloudinary.

        Reads the CLOUDINARY_ADMIN_ASYNC Django setting:
          - False (default): synchronous upload in-thread.
          - True (production): base64-encodes the file, saves the model
            immediately, and dispatches the upload to a Celery worker.
        """
        from django.conf import settings

        async_mode = getattr(settings, "CLOUDINARY_ADMIN_ASYNC", False)

        if async_mode:
            try:
                self._process_cloudinary_uploads_async(request, obj, form, change)
            except Exception as exc:
                logger.error(
                    "CloudinaryUploadAdminMixin (async): enqueue failed — %s. "
                    "Falling back to sync path.",
                    exc,
                )
                # Graceful degradation: if enqueue fails, fall through to sync
                try:
                    self._process_cloudinary_uploads(request, obj, form, change)
                except Exception as sync_exc:
                    logger.error(
                        "CloudinaryUploadAdminMixin sync fallback also failed — %s.",
                        sync_exc,
                    )
        else:
            try:
                self._process_cloudinary_uploads(request, obj, form, change)
            except Exception as exc:
                logger.error(
                    "CloudinaryUploadAdminMixin.save_model: upload failed -- %s. "
                    "Falling back to default save (no Cloudinary URL).",
                    exc,
                )
        super().save_model(request, obj, form, change)

    def _process_cloudinary_uploads(
        self,
        request: Any,
        obj: Any,
        form: Any,
        change: bool,
    ) -> None:
        """Process all Cloudinary field uploads for this admin save."""

        for field_name, (folder, asset_type) in self.cloudinary_fields.items():
            # Check if the admin form has a new file for this field
            file_obj = form.cleaned_data.get(field_name)

            if not file_obj:
                continue

            # Django admin passes either a File object (new upload) or a string
            # URL (existing value retained). Only process actual file uploads.
            if not hasattr(file_obj, "read"):
                continue

            try:
                logger.info(
                    "CloudinaryUploadAdminMixin: uploading %s.%s to folder=%s "
                    "asset_type=%s (admin user=%s)",
                    obj.__class__.__name__,
                    field_name,
                    folder,
                    asset_type,
                    getattr(request.user, "email", "?"),
                )

                # ✅ FIXED: was calling upload_to_cloudinary_from_admin (NameError)
                secure_url = upload_to_cloudinary_from_admin_sync(
                    file_obj=file_obj,
                    folder=folder,
                    asset_type=asset_type,
                    user=request.user,
                )

                # ── Smart URL field routing ──────────────────────────────────
                # The Django image field (e.g. 'image', 'background_image') is
                # NOT updated — we store only the Cloudinary URL.
                # Map each upload field → its corresponding cloudinary_url field:
                #   image            → cloudinary_url
                #   background_image → background_cloudinary_url
                #   avatar           → cloudinary_url
                # Default fallback: <field_name>_cloudinary_url or cloudinary_url
                _URL_FIELD_MAP = {
                    "image":            "cloudinary_url",
                    "background_image": "background_cloudinary_url",
                    "avatar":           "cloudinary_url",
                }
                url_field = _URL_FIELD_MAP.get(field_name, f"{field_name}_cloudinary_url")

                # Only set the cloudinary URL field if it exists on the model
                if hasattr(obj, url_field):
                    setattr(obj, url_field, secure_url)
                else:
                    # Fallback: set the raw field itself (older models)
                    setattr(obj, field_name, secure_url)

                # ── Prevent Double Upload ───────────────────────────────────────────
                # After successful manual upload to Cloudinary, we clear the file
                # from form.cleaned_data. This prevents the default storage engine
                # (which is also Cloudinary) from trying to upload the "consumed"
                # file again during super().save_model(request, obj, form, change).
                # This explicitly fixes the "cloudinary.exceptions.BadRequest: Empty file"
                # error caused by re-reading an un-seekable or already-consumed stream.
                form.cleaned_data[field_name] = None

                logger.info(
                    "CloudinaryUploadAdminMixin: ✅ uploaded %s.%s → %s → %s...",
                    obj.__class__.__name__,
                    field_name,
                    url_field,
                    secure_url[:60],
                )

                # Log audit event for admin upload
                self._log_cloudinary_admin_upload(
                    request=request,
                    obj=obj,
                    field_name=field_name,
                    url_field=url_field,
                    secure_url=secure_url,
                    asset_type=asset_type,
                )

            except Exception as exc:
                logger.error(
                    "CloudinaryUploadAdminMixin: upload FAILED for %s.%s: %s",
                    obj.__class__.__name__,
                    field_name,
                    exc,
                )
                raise

    def _process_cloudinary_uploads_async(
        self,
        request: Any,
        obj: Any,
        form: Any,
        change: bool,
    ) -> None:
        """
        Phase 6 ASYNC path: base64-encode files and dispatch to Celery.

        Loops over cloudinary_fields. For each field with a new file upload:
          1. Read and base64-encode the file bytes (serializable for Redis/RabbitMQ).
          2. Clear the field from form.cleaned_data so Django's default storage
             backend does not attempt a second upload.
          3. Dispatch ``process_admin_cloudinary_upload.apply_async()``.

        The admin HTTP response is returned immediately after super().save_model().
        The Celery task handles the Cloudinary HTTP call and DB field update.

        Note: obj.pk must already exist before this method is called (which is
        guaranteed since Django admin calls save_model() after the instance is
        committed in a transaction — i.e., obj.pk is always set at this point).
        """
        import base64
        from apps.common.tasks.cloudinary import process_admin_cloudinary_upload

        _URL_FIELD_MAP = {
            "image":            "cloudinary_url",
            "background_image": "background_cloudinary_url",
            "avatar":           "cloudinary_url",
        }

        admin_user = request.user
        admin_user_id    = str(getattr(admin_user, "pk", None) or "")
        admin_user_email = getattr(admin_user, "email", None)
        model_path = (
            f"{obj.__class__.__module__}.{obj.__class__.__name__}"
        )

        for field_name, (folder, asset_type) in self.cloudinary_fields.items():
            file_obj = form.cleaned_data.get(field_name)

            if not file_obj or not hasattr(file_obj, "read"):
                continue  # No new file — skip

            try:
                # Read file bytes (ensure seekable)
                if hasattr(file_obj, "seek"):
                    file_obj.seek(0)
                file_bytes = file_obj.read()
                file_b64   = base64.b64encode(file_bytes).decode("ascii")
                file_name  = getattr(file_obj, "name", "upload.bin")

                url_field = _URL_FIELD_MAP.get(
                    field_name, f"{field_name}_cloudinary_url"
                )

                # Clear from form so Django storage doesn't double-upload
                form.cleaned_data[field_name] = None

                # Dispatch to Celery — returns immediately
                process_admin_cloudinary_upload.apply_async(
                    kwargs={
                        "model_path":       model_path,
                        "object_pk":        str(obj.pk),
                        "field_name":       field_name,
                        "url_field":        url_field,
                        "folder":           folder,
                        "asset_type":       asset_type,
                        "file_b64":         file_b64,
                        "file_name":        file_name,
                        "admin_user_id":    admin_user_id,
                        "admin_user_email": admin_user_email,
                    },
                    retry=False,
                    ignore_result=True,
                )
                logger.info(
                    "CloudinaryUploadAdminMixin (async): task enqueued for "
                    "%s.%s pk=%s (%.1f KB)",
                    obj.__class__.__name__,
                    field_name,
                    obj.pk,
                    len(file_bytes) / 1024,
                )

            except Exception as exc:
                logger.error(
                    "CloudinaryUploadAdminMixin (async): enqueue FAILED for "
                    "%s.%s: %s",
                    obj.__class__.__name__,
                    field_name,
                    exc,
                )
                raise  # Caller (save_model) catches and falls back to sync

    def _log_cloudinary_admin_upload(
        self,
        request: Any,
        obj: Any,
        field_name: str,
        url_field: str,
        secure_url: str,
        asset_type: str,
    ) -> None:
        """Log admin file upload as ADMIN_ACTION audit event."""
        try:
            from apps.audit_logs.services.audit import AuditService
            from apps.audit_logs.models import EventType, EventCategory
            AuditService.log(
                event_type=EventType.ADMIN_ACTION,
                event_category=EventCategory.ADMIN,
                action=(
                    f"Admin uploaded {asset_type} to Cloudinary: "
                    f"{obj.__class__.__name__}.{field_name} → {url_field}"
                ),
                actor=request.user,
                request=request,
                resource_type=obj.__class__.__name__,
                resource_id=str(obj.pk) if obj.pk else None,
                new_values={
                    url_field: secure_url[:120],
                    "asset_type": asset_type,
                    "source_field": field_name,
                },
                metadata={
                    "cloudinary_admin_upload": True,
                    "field_name": field_name,
                    "url_field": url_field,
                },
                is_compliance=True,
            )
        except Exception as exc:
            logger.debug(
                "CloudinaryUploadAdminMixin: audit log failed (non-fatal): %s", exc
            )


# ─────────────────────────────────────────────────────────────────────────────
# upload_to_cloudinary_from_admin() — add to utils/cloudinary.py
# ─────────────────────────────────────────────────────────────────────────────
# This function is defined here for convenience and re-exported.
# The canonical definition lives in apps/common/utils/cloudinary.py.

def upload_to_cloudinary_from_admin_sync(
    file_obj: Any,
    folder: str,
    asset_type: str = "generic_image",
    user: Any = None,
) -> str:
    """
    Synchronous Cloudinary upload for Django admin panel use.

    Uploads the file object directly to Cloudinary using the Upload API.
    Triggers eager transformations asynchronously so the admin save isn't slow.

    Args:
        file_obj  : Django InMemoryUploadedFile or TemporaryUploadedFile
        folder    : Cloudinary folder string (e.g. "fashionistar/categories/images")
        asset_type: Key from _ASSET_CONFIGS (e.g. "category", "product_image")
        user      : The Django admin user (for audit logging)

    Returns:
        str: Cloudinary secure_url

    Raises:
        Exception: If Cloudinary upload fails
    """
    import cloudinary.uploader
    from apps.common.utils.cloudinary import _ASSET_CONFIGS

    config = _ASSET_CONFIGS.get(asset_type, _ASSET_CONFIGS.get("generic_image", {}))
    eager  = config.get("eager", [])

    # Read file content (Django's upload file is a file-like object)
    if hasattr(file_obj, "seek"):
        file_obj.seek(0)

    try:
        result = cloudinary.uploader.upload(
            file_obj,
            folder=folder,
            resource_type="auto",   # Cloudinary auto-detects image vs video vs raw
            eager=eager,
            eager_async=True,       # Non-blocking — triggers in background
            use_filename=True,
            unique_filename=True,
            overwrite=False,
            quality="auto",
            fetch_format="auto",
        )
    finally:
        # Crucial for preventing "Empty file" errors when Django's save_model
        # attempts to pass this file_obj to the default storage backend afterwards.
        if hasattr(file_obj, "seek"):
            file_obj.seek(0)

    secure_url = result.get("secure_url", "")
    if not secure_url:
        raise ValueError(f"Cloudinary upload returned no secure_url: {result}")

    return secure_url
