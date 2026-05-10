"""
CloudinaryProviderConfig — Admin-switchable Cloudinary media config singleton.

Replaces hardcoded settings for upload presets and signature TTL.
Credentials (CLOUDINARY_CLOUD_NAME, API_KEY, API_SECRET) stay in .env —
this model only stores operational settings and circuit state.
"""
from __future__ import annotations

from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.providers.models.base import AbstractProviderConfig


class CloudinaryProviderConfig(AbstractProviderConfig):
    """
    Singleton controlling Cloudinary media upload behaviour.

    All credentials (cloud_name, api_key, api_secret) are read from
    Django settings / .env to keep secrets out of the DB.
    This model stores only the operational knobs and circuit state.
    """

    upload_preset_images = models.CharField(
        max_length=120,
        default="fashionistar_images",
        verbose_name=_("Image Upload Preset"),
        help_text=_("Cloudinary upload preset used for all image uploads."),
    )
    upload_preset_videos = models.CharField(
        max_length=120,
        default="fashionistar_videos",
        verbose_name=_("Video Upload Preset"),
        help_text=_("Cloudinary upload preset used for all video uploads."),
    )
    signature_ttl_seconds = models.PositiveIntegerField(
        default=3300,
        verbose_name=_("Presign TTL (seconds)"),
        help_text=_(
            "How long a presigned upload token is valid (max 3600 per Cloudinary). "
            "3300 (55 min) gives safety margin before the 1-hour limit."
        ),
    )
    max_image_bytes = models.PositiveIntegerField(
        default=10_485_760,  # 10 MB
        verbose_name=_("Max Image Size (bytes)"),
        help_text=_("Maximum allowed image upload size in bytes."),
    )
    max_video_bytes = models.PositiveIntegerField(
        default=104_857_600,  # 100 MB
        verbose_name=_("Max Video Size (bytes)"),
        help_text=_("Maximum allowed video upload size in bytes."),
    )
    enabled = models.BooleanField(
        default=True,
        verbose_name=_("Enabled"),
        help_text=_("Disable to stop accepting media uploads (maintenance mode)."),
    )

    class Meta:
        app_label = "providers"
        verbose_name = _("Cloudinary Provider Configuration")
        verbose_name_plural = _("Cloudinary Provider Configuration")

    def __str__(self) -> str:
        status = "✅ Enabled" if self.enabled else "❌ Disabled"
        return f"Cloudinary Config [{status}] preset={self.upload_preset_images}"
