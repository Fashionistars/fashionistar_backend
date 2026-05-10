# apps/providers/MirrorSize/__init__.py
"""
MirrorSize Body Measurement Provider Sub-Package.

Provides the Fashionistar MirrorSize driver for AI-powered precision body
measurement capture.  MirrorSize enables clients to capture accurate body
measurements via smartphone camera, which are used to ensure perfect fit
for custom and semi-custom tailoring orders.

Driver:
    MirrorSizeClient — HTTP driver for the MirrorSize mobile-browser measurement API.
        - Generates a mobile-browser access code + QR URL for scanning.
        - Fetches completed measurement data by access code.
        - Sync only (DRF views / management commands).

Business Rules:
    - A measurement session fee (₦1,000 default, admin-configurable via
      ``GlobalPlatformSettings.measurement_fee_ngn``) is charged to the
      client's wallet before a session is initiated.
    - Measurements are stored in ``apps.measurements.models.BodyMeasurement``
      and gated at checkout for tailoring products.
    - Only active, verified measurements within 90 days are accepted at checkout.

Environment Variables (configured via Django Admin → Providers → MirrorSize Config
OR as Django settings / .env as a fallback):
    MIRRORSIZE_API_KEY
    MIRRORSIZE_MERCHANT_ID
    MIRRORSIZE_PRODUCT_NAME (default: "GET_MEASURED")
    MIRRORSIZE_BROWSER_API_BASE_URL (default: "https://api.user.mirrorsize.com")
    MIRRORSIZE_USER_HOME_BASE_URL (default: "https://user.mirrorsize.com/home")

Usage::

    from apps.providers.MirrorSize import MirrorSizeClient, MirrorSizeProviderError

    client = MirrorSizeClient.from_settings()
    result = client.generate_mobile_browser_access_code(
        email="client@example.com",
        name="Jane Doe",
        reference="ORD-001",
    )
    # result["access_code"] → scan or share measurement_url / qr_code
"""

from apps.providers.MirrorSize.mirrorsize_provider import (
    MirrorSizeClient,
    MirrorSizeProviderError,
)

__all__ = [
    "MirrorSizeClient",
    "MirrorSizeProviderError",
]
