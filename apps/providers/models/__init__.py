# apps/providers/models/__init__.py
"""
Provider Configuration DB Models — Barrel Export.

This module re-exports every ``ProviderConfig`` model so that any module in
the backend can import provider configs from a single stable namespace:

    ``from apps.providers.models import KYCProviderConfig``

Models:
    KYCProviderConfig          — Config for KYC gateway selection + credentials.
    SMSProviderConfig          — Config for SMS gateway selection + credentials.
    EmailProviderConfig        — Config for transactional email gateway selection.
    CloudinaryProviderConfig   — Config for Cloudinary media upload credentials.
    MirrorSizeProviderConfig   — Config for MirrorSize measurement API credentials.

Note:
    ``PaymentProviderConfig`` is intentionally absent here — each payment driver
    (Paystack, Flutterwave, OlivePay) reads credentials directly from Django
    settings / environment variables for PCI compliance.  Payment keys must
    NEVER be stored in the database.
"""

from apps.providers.models.cloudinary_config import CloudinaryProviderConfig
from apps.providers.models.email_config import EmailProviderConfig
from apps.providers.models.kyc_config import KYCProviderConfig
from apps.providers.models.mirrorsize_config import MirrorSizeProviderConfig
from apps.providers.models.sms_config import SMSProviderConfig

__all__ = [
    "CloudinaryProviderConfig",
    "EmailProviderConfig",
    "KYCProviderConfig",
    "MirrorSizeProviderConfig",
    "SMSProviderConfig",
]
