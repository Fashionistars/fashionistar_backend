"""
Cloudinary media provider — presign upload tokens and manage asset lifecycle.

Credentials from Django settings:
    CLOUDINARY_CLOUD_NAME = env("CLOUDINARY_CLOUD_NAME")
    CLOUDINARY_API_KEY    = env("CLOUDINARY_API_KEY")
    CLOUDINARY_API_SECRET = env("CLOUDINARY_API_SECRET")

Operational config from CloudinaryProviderConfig (DB singleton).
"""
from __future__ import annotations

import hashlib
import logging
import time
from typing import Literal

from django.conf import settings

from apps.providers.circuit_breaker import CircuitBreaker

logger = logging.getLogger("application")

_breaker = CircuitBreaker(provider_key="cloudinary", failure_threshold=3)

MediaKind = Literal["image", "video"]


class CloudinaryProvider:
    """
    Facade for Cloudinary media operations with circuit breaker protection.

    Uses the `cloudinary` SDK which is sync-only. Async callers should wrap
    with asyncio.to_thread.
    """

    def __init__(self, config) -> None:
        """
        Args:
            config: CloudinaryProviderConfig instance (from DB).
        """
        self._config = config
        # Pull credentials from settings (never DB)
        self._cloud_name: str = getattr(settings, "CLOUDINARY_CLOUD_NAME", "")
        self._api_key: str = getattr(settings, "CLOUDINARY_API_KEY", "")
        self._api_secret: str = getattr(settings, "CLOUDINARY_API_SECRET", "")

    # ── Presign Upload Parameters ──────────────────────────────────────────────

    def generate_presigned_params(
        self,
        *,
        kind: MediaKind = "image",
        folder: str = "fashionistar",
        public_id: str | None = None,
    ) -> dict:
        """
        Generate a signed upload parameter set for direct browser-to-Cloudinary upload.

        Returns the dict the frontend must POST to Cloudinary's upload endpoint.
        Signature is HMAC-SHA256 over a canonical string of parameters.
        """
        _breaker.call(lambda: None)  # raises if circuit is open

        preset = (
            self._config.upload_preset_images if kind == "image"
            else self._config.upload_preset_videos
        )
        timestamp = int(time.time())
        ttl = self._config.signature_ttl_seconds

        params: dict = {
            "timestamp": timestamp,
            "upload_preset": preset,
            "folder": folder,
        }
        if public_id:
            params["public_id"] = public_id

        # Build canonical string (sorted keys, excluding signature/api_key)
        sorted_params = "&".join(f"{k}={v}" for k, v in sorted(params.items()))
        to_sign = sorted_params + self._api_secret
        signature = hashlib.sha256(to_sign.encode("utf-8")).hexdigest()

        logger.info(
            "CloudinaryProvider: presigned params generated kind=%s folder=%s ttl=%s",
            kind, folder, ttl,
        )
        return {
            **params,
            "signature": signature,
            "api_key": self._api_key,
            "cloud_name": self._cloud_name,
        }

    # ── Delete Asset ──────────────────────────────────────────────────────────

    def delete_asset(self, public_id: str, resource_type: str = "image") -> dict:
        """
        Delete a Cloudinary asset by public_id.
        Wraps the cloudinary.uploader.destroy call with circuit breaker protection.
        """
        import cloudinary
        import cloudinary.uploader

        def _call():
            cloudinary.config(
                cloud_name=self._cloud_name,
                api_key=self._api_key,
                api_secret=self._api_secret,
                secure=True,
            )
            return cloudinary.uploader.destroy(public_id, resource_type=resource_type)

        result = _breaker.call(_call)
        logger.info("CloudinaryProvider.delete_asset: public_id=%s result=%s", public_id, result)
        return result
