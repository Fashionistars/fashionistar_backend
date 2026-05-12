# apps/providers/KYC/__init__.py
"""
KYC (Know Your Customer) Provider Sub-Package.

Provides three identity verification drivers for Nigerian NDPR-compliant
KYC processing.  All drivers implement ``AbstractKYCProvider`` from
``apps.providers.KYC.base``.

Drivers:
    SmileIdentityProvider — Smile Identity v2 (BVN, NIN, biometric liveness).
    DojahProvider         — Dojah Nigeria (BVN, NIN, phone + face match).
    YouverifyProvider     — Youverify Nigeria (BVN, NIN, CAC business lookup).

NDPR Compliance (all drivers):
    - Raw BVN / NIN numbers are NEVER transmitted to any provider.
    - Only the last 4 digits (``last4``) are used as a masked reference.
    - The provider's job/request ID is stored as ``provider_reference`` for
      webhook reconciliation and audit trail logging.

Selection:
    The active provider is resolved at runtime from the ``KYCProviderConfig``
    DB record (admin-managed) via ``apps.providers.cache.get_kyc_provider_config``.

Usage (via service layer — preferred)::

    from apps.kyc.services.kyc_service import KycService
    result = await KycService.verify_bvn(user=user, bvn_hash=bvn_hash, last4=last4)

Direct instantiation (for testing only)::

    from apps.providers.KYC.smileid import SmileIdentityProvider
    config = KYCProviderConfig.objects.get(provider_slug="smileid", is_active=True)
    provider = SmileIdentityProvider(config)
    result = provider.verify_bvn(bvn_hash=..., last4="1234")
"""

from apps.providers.KYC.base import AbstractKYCProvider, KYCVerificationResult, WebhookResult
from apps.providers.KYC.dojah import DojahProvider
from apps.providers.KYC.smileid import SmileIdentityProvider
from apps.providers.KYC.youverify import YouverifyProvider
from django.utils.module_loading import import_string

# ── Django Admin Choices ───────────────────────────────────────────────────────

KYC_PROVIDER_CHOICES: list[tuple[str, str]] = [
    ("smileid", "Smile Identity (West/East Africa — BVN + NIN + Liveness)"),
    ("dojah", "Dojah Nigeria (BVN + NIN + Face Match)"),
    ("youverify", "Youverify (Identity + Document + CAC Verification)"),
]

# Mapping: slug → dotted Python import path for the provider driver class
_KYC_CLASS_PATH_MAP: dict[str, str] = {
    "smileid": "apps.providers.KYC.smileid.SmileIdentityProvider",
    "dojah": "apps.providers.KYC.dojah.DojahProvider",
    "youverify": "apps.providers.KYC.youverify.YouverifyProvider",
}

_KYC_LABEL_LOOKUP: dict[str, str] = dict(KYC_PROVIDER_CHOICES)


def get_kyc_provider_label(provider_slug: str) -> str:
    """Return the human-readable display name for a KYC provider slug.

    Used in ``KYCProviderConfig.__str__`` and admin list displays.

    Args:
        provider_slug: Short identifier (e.g. ``"dojah"``, ``"smileid"``).

    Returns:
        str: Display name, or the ``provider_slug`` itself if not found.
    """
    return _KYC_LABEL_LOOKUP.get(provider_slug, provider_slug)


def get_kyc_provider_class_path(provider_slug: str) -> str:
    """Return the dotted Python import path for a KYC provider driver class.

    Used by ``KYCProviderConfig.get_provider_class_path()`` to resolve which
    driver class to instantiate at runtime.

    Args:
        provider_slug: Short provider identifier (e.g. ``"dojah"``).

    Returns:
        str: Dotted Python class path, or ``""`` if the slug is unknown.
    """
    return _KYC_CLASS_PATH_MAP.get(provider_slug, "")


def load_kyc_provider(config):
    """Instantiate the active KYC provider driver from a KYCProviderConfig row.

    The service layer calls this loader instead of importing concrete providers
    directly. This keeps provider switching admin/database-driven and cacheable.
    """
    provider_path = config.get_provider_class_path()
    if not provider_path:
        raise ValueError(f"Unsupported KYC provider slug: {config.provider_slug!r}")
    provider_class = import_string(provider_path)
    return provider_class(config)


# ── Webhook Signature Header Lookup ───────────────────────────────────────────

# Each KYC provider signs webhook deliveries using a different HTTP header.
_KYC_WEBHOOK_HEADER_MAP: dict[str, str] = {
    "smileid": "X-Smile-Identity-Signature",
    "dojah": "X-Dojah-Signature",
    "youverify": "X-Youverify-Signature",
}


def get_kyc_webhook_header(provider_slug: str) -> str:
    """Return the HTTP header name that a KYC provider uses to send its HMAC signature.

    Used in ``KycWebhookView`` to extract the signature from ``request.META``
    before performing constant-time HMAC comparison.

    Django converts HTTP header names to META keys by uppercasing and replacing
    hyphens with underscores, then prepending ``HTTP_``.  Example::

        get_kyc_webhook_header("dojah")  # → "X-Dojah-Signature"
        # KycWebhookView converts to META key: "HTTP_X_DOJAH_SIGNATURE"

    Args:
        provider_slug: Short provider identifier (e.g. ``"dojah"``, ``"smileid"``).

    Returns:
        str: The HTTP header name, or ``"X-Provider-Signature"`` as a safe fallback.
    """
    return _KYC_WEBHOOK_HEADER_MAP.get(provider_slug, "X-Provider-Signature")


__all__ = [
    # Abstract base + result types
    "AbstractKYCProvider",
    "KYCVerificationResult",
    "WebhookResult",
    # Driver classes
    "SmileIdentityProvider",
    "DojahProvider",
    "YouverifyProvider",
    # Registry helpers (consumed by KYCProviderConfig)
    "KYC_PROVIDER_CHOICES",
    "get_kyc_provider_label",
    "get_kyc_provider_class_path",
    "load_kyc_provider",
    # Webhook helpers (consumed by KycWebhookView)
    "get_kyc_webhook_header",
]
