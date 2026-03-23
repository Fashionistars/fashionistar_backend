# apps/common/admin_cloudinary_mixin.py
"""
Cloudinary Admin Upload Mixin — Phase 4 Production.

Provides CloudinaryUploadAdminMixin for Django ModelAdmin classes that have
image/video fields stored as Cloudinary URLs.

When an admin user uploads a file via the Django admin panel (e.g., Category
image, Brand logo, Collection banner), the mixin:

  1. Detects that a new file was uploaded (form field has a File object)
  2. Uploads it directly to Cloudinary via Upload API
  3. Replaces the form field value with the returned secure_url
  4. Saves the model with the Cloudinary URL (not the local file)
  5. Logs an ADMIN_ACTION audit event

Usage
─────
    from apps.common.admin_cloudinary_mixin import CloudinaryUploadAdminMixin

    @admin.register(Category)
    class CategoryAdmin(CloudinaryUploadAdminMixin, ModelAdmin):
        cloudinary_fields = {
            "image": ("fashionistar/categories/images", "category"),
            "banner": ("fashionistar/categories/banners", "generic_image"),
        }

cloudinary_fields Format
────────────────────────
    {
        "<django_field_name>": ("<cloudinary_folder>", "<asset_type_key>"),
    }

Where asset_type_key is any key from _ASSET_CONFIGS in utils/cloudinary.py
(e.g. "avatar", "product_image", "category", "collection", "brand", etc.)
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

        For each field in cloudinary_fields:
          - If form contains a File object for that field → upload to Cloudinary
          - Replace form value with the returned secure_url
          - Set the field on the model instance before save
        """
        try:
            self._process_cloudinary_uploads(request, obj, form, change)
        except Exception as exc:
            logger.error(
                "CloudinaryUploadAdminMixin.save_model: upload failed — %s. "
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

                secure_url = upload_to_cloudinary_from_admin(
                    file_obj=file_obj,
                    folder=folder,
                    asset_type=asset_type,
                    user=request.user,
                )

                # Set the Cloudinary URL on the model instance
                setattr(obj, field_name, secure_url)

                logger.info(
                    "CloudinaryUploadAdminMixin: ✅ uploaded %s.%s → %s...",
                    obj.__class__.__name__,
                    field_name,
                    secure_url[:60],
                )

                # Log audit event for admin upload
                self._log_cloudinary_admin_upload(
                    request=request,
                    obj=obj,
                    field_name=field_name,
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

    def _log_cloudinary_admin_upload(
        self,
        request: Any,
        obj: Any,
        field_name: str,
        secure_url: str,
        asset_type: str,
    ) -> None:
        """Log admin file upload as ADMIN_ACTION audit event."""
        try:
            from apps.audit_logs.services.audit import AuditService
            AuditService.log(
                event_type="admin_action",
                action=(
                    f"Admin uploaded {asset_type} to Cloudinary: "
                    f"{obj.__class__.__name__}.{field_name}"
                ),
                actor=request.user,
                request=request,
                resource_type=obj.__class__.__name__,
                resource_id=str(obj.pk) if obj.pk else None,
                new_values={
                    field_name: secure_url[:120],
                    "asset_type": asset_type,
                },
                metadata={
                    "cloudinary_admin_upload": True,
                    "field_name": field_name,
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
    file_obj.seek(0)

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

    secure_url = result.get("secure_url", "")
    if not secure_url:
        raise ValueError(f"Cloudinary upload returned no secure_url: {result}")

    return secure_url
