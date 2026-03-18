# apps/common/serializers.py
"""
Common App Serializers — Phase 7B.

Provides input validation serializers for:
  - CloudinaryPresignView (PresignRequestSerializer)
  - CloudinaryWebhookView (WebhookPayloadSerializer — validation-only gate)
  - HealthCheckView has no query params and needs no serializer (GET only).
"""

from __future__ import annotations

from rest_framework import serializers


# ─── Derived at import time from cloudinary utils ────────────────────────────

def _valid_asset_types() -> list[str]:
    """Return valid asset types from _ASSET_CONFIGS (lazy to avoid import cycle)."""
    try:
        from apps.common.utils.cloudinary import _ASSET_CONFIGS
        return sorted(_ASSET_CONFIGS.keys())
    except Exception:
        # Fallback to known defaults if cloudinary utils can't be imported
        return ["avatar", "measurement", "product_image", "product_video"]


class PresignRequestSerializer(serializers.Serializer):
    """
    Input serializer for POST /api/v1/upload/presign/

    Validates the ``asset_type`` field before passing to
    ``generate_cloudinary_upload_params()``.  Replaces the previous raw
    ``request.data.get("asset_type", "avatar")`` pattern with typed DRF
    validation that surfaces a proper 400 with field-level errors.

    Valid asset_types are derived dynamically from _ASSET_CONFIGS so the
    serializer stays in sync if new asset types are added.
    """
    asset_type = serializers.ChoiceField(
        choices=_valid_asset_types(),
        default="avatar",
        help_text=(
            "Type of Cloudinary asset to upload. "
            "One of: avatar, product_image, product_video, measurement."
        ),
    )

    class Meta:
        ref_name = "CommonPresignRequest"


class WebhookPayloadSerializer(serializers.Serializer):
    """
    Input serializer for POST /api/v1/upload/webhook/cloudinary/

    NOTE: HMAC-SHA256 signature validation (``X-Cld-Signature`` header) is
    the PRIMARY security gate — this serializer is a SECONDARY structural
    validator that runs AFTER the signature is confirmed valid.

    Fields are all optional/have defaults because Cloudinary sends different
    payload shapes depending on the notification_type (upload vs eager).
    Unknown fields are ignored (no strict schema enforcement beyond these).
    """
    notification_type = serializers.CharField(
        required=False,
        default="",
        help_text="Cloudinary notification type: 'upload', 'eager', etc.",
    )
    public_id = serializers.CharField(
        required=False,
        default="",
        help_text="Cloudinary public_id of the uploaded asset.",
    )
    secure_url = serializers.URLField(
        required=False,
        default="",
        allow_blank=True,
        help_text="HTTPS URL of the uploaded asset.",
    )
    resource_type = serializers.CharField(
        required=False,
        default="image",
        help_text="Cloudinary resource type: 'image', 'video', 'raw'.",
    )
    format = serializers.CharField(
        required=False,
        default="",
        help_text="File format (e.g. 'jpg', 'mp4').",
    )
    bytes = serializers.IntegerField(
        required=False,
        default=0,
        min_value=0,
        help_text="File size in bytes.",
    )

    class Meta:
        ref_name = "CommonWebhookPayload"
