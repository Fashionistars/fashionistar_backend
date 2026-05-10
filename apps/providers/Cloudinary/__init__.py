# apps/providers/Cloudinary/__init__.py
"""
Cloudinary Media Provider Sub-Package.

Provides the Fashionistar Cloudinary driver for all image and video asset
upload, transformation, and CDN delivery operations.

Driver:
    CloudinaryProvider — wraps the official ``cloudinary`` SDK with:
        - Structured error handling via ``ProviderHTTPError``.
        - Signed uploads using the Cloudinary API secret.
        - Configurable folder organisation per asset type
          (products, avatars, vendor_banners, kyc_documents).
        - Async-compatible helper for use in Django-Ninja views via
          ``asyncio.to_thread``.

Environment Variables (configured via Django Admin → Providers → Cloudinary Config
OR as Django settings / .env as a fallback):
    CLOUDINARY_CLOUD_NAME
    CLOUDINARY_API_KEY
    CLOUDINARY_API_SECRET

Usage::

    from apps.providers.Cloudinary.cloudinary_provider import CloudinaryProvider
    result = CloudinaryProvider.upload(file_path="/tmp/avatar.jpg", folder="avatars")
    url = result["secure_url"]
"""

from apps.providers.Cloudinary.cloudinary_provider import CloudinaryProvider

__all__ = ["CloudinaryProvider"]
