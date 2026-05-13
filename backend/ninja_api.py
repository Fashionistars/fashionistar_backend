# backend/ninja_api.py
"""
Fashionistar — Central Django-Ninja API (Async).

All high-performance async endpoints are registered here.
Mounted at: /api/v1/ninja/

Usage in backend/urls.py:
    from backend.ninja_api import ninja_api
    urlpatterns += [path("api/v1/ninja/", ninja_api.urls)]

Authentication:
    All routes use JWT Bearer by default.
    Unauthenticated endpoints explicitly override with auth=None.
"""
from ninja import NinjaAPI
from ninja.security import HttpBearer


class AsyncJWTAuth(HttpBearer):
    """
    JWT Bearer authentication for Ninja endpoints.

    Validates the same SimpleJWT access token used by DRF.
    Returns the UnifiedUser instance so request.auth is the user.
    """

    async def authenticate(self, request, token: str):
        try:
            from rest_framework_simplejwt.tokens import AccessToken
            from apps.authentication.models import UnifiedUser

            # Validate token
            decoded = AccessToken(token)
            user_id = decoded.get("user_id")
            if not user_id:
                return None

            # Async ORM lookup. Reverse OneToOne profiles are hydrated here so
            # Ninja read handlers can use request.auth.client_profile,
            # request.auth.vendor_profile, and request.auth.kyc_submission
            # without issuing another profile/KYC query.
            user = await (
                UnifiedUser.objects.select_related(
                    "client_profile",
                    "vendor_profile",
                    "kyc_submission",
                )
                .aget(pk=user_id, is_active=True)
            )
            return user

        except Exception:
            return None





# ========================================================================
# V1 Ninja API — Asynchronous Endpoints (High-Concurrency, ASGI-Ready)
# ========================================================================
# All Ninja endpoints MUST be mounted under /api/v1/ninja/ to:
#   1. Stay on v1 (uniform versioning across the whole API)
#   2. Avoid URL collisions with DRF v1 endpoints at /api/v1/auth/
#   3. Make versioning explicit: /api/v1/ninja/auth/*, /api/v1/ninja/products/*, etc.





# ── Central Ninja API ──────────────────────────────────────────────────────────
ninja_api = NinjaAPI(
    title="Fashionistar Async API",
    version="1.0.0",
    description=(
        "High-performance async endpoints for Fashionistar.\n\n"
        "All routes require `Authorization: Bearer <access_token>`.\n"
        "Obtain tokens from the DRF auth endpoint: `POST /api/v1/auth/login/`."
    ),
    auth=AsyncJWTAuth(),
    urls_namespace="ninja",
    docs_url="/docs/",
)






"""
Django Ninja API Instance — Async V1.

Registers async domain routers for high-concurrency reads:
  - /api/v1/ninja/products/   → catalog reads, featured, search, wishlist
  - /api/v1/ninja/catalog/    → category/brand lists
  - /api/v1/ninja/cart/       → cart reads
  - Additional domains wired as they are built.
"""
import logging
from ninja import NinjaAPI

logger = logging.getLogger('application')

# ── Singleton guard ───────────────────────────────────────────────────────────
_api_instance = None


def _get_api() -> NinjaAPI:
    """Returns the NinjaAPI singleton with all domain routers registered."""
    global _api_instance
    if _api_instance is not None:
        return _api_instance

    _api_instance = NinjaAPI(
        title="Fashionistar API V1",
        version="1.0.0",
        description="Async API using Django Ninja — high-concurrency reads.",
        urls_namespace='authentication_v1',
    )

    # ── Product domain ─────────────────────────────────────────────────────────
    try:
        from apps.product.apis.async_.product_views import router as product_router
        _api_instance.add_router("/products/", product_router)
        logger.info("✅ NinjaAPI: product router registered at /api/v1/ninja/products/")
    except Exception as exc:  # pragma: no cover
        logger.error("❌ NinjaAPI: product router FAILED to register: %s", exc)

    # ── Catalog domain ─────────────────────────────────────────────────────────
    try:
        from apps.catalog.apis.async_.catalog_views import router as catalog_router
        _api_instance.add_router("/catalog/", catalog_router)
        logger.info("✅ NinjaAPI: catalog router registered at /api/v1/ninja/catalog/")
    except Exception as exc:
        logger.info("ℹ️  NinjaAPI: catalog router not available (%s)", exc)

    # ── Cart domain ────────────────────────────────────────────────────────────
    try:
        from apps.cart.apis.async_.cart_views import router as cart_router
        _api_instance.add_router("/cart/", cart_router)
        logger.info("✅ NinjaAPI: cart router registered at /api/v1/ninja/cart/")
    except Exception as exc:
        logger.info("ℹ️  NinjaAPI: cart router not available (%s)", exc)

    # ── Vendor domain ──────────────────────────────────────────────────────────
    try:
        from apps.vendor.apis.async_.dashboard_views import router as vendor_async_router
        _api_instance.add_router("/vendor/", vendor_async_router)
        logger.info("✅ NinjaAPI: vendor dashboard router registered at /api/v1/ninja/vendor/")
    except Exception as exc:
        logger.info("ℹ️  NinjaAPI: vendor async router not available (%s)", exc)

    # ── Client domain ──────────────────────────────────────────────────────────
    try:
        from apps.client.apis.async_.dashboard_views import router as client_async_router
        _api_instance.add_router("/client/", client_async_router)
        logger.info("✅ NinjaAPI: client dashboard router registered at /api/v1/ninja/client/")
    except Exception as exc:
        logger.info("ℹ️  NinjaAPI: client async router not available (%s)", exc)

    logger.info("✅ NinjaAPI V1 initialized (namespace=authentication_v1, path=/api/v1/ninja/)")
    return _api_instance


# ── Module-level export (used by urls.py) ─────────────────────────────────────
api = _get_api()











# ── Register Domain Routers ────────────────────────────────────────────────────

# Common reference-data domain: /api/v1/ninja/common/
from apps.common.apis.async_.reference_views import router as common_router
ninja_api.add_router("/common/", common_router)

# Client domain: /api/v1/ninja/client/
from apps.client.apis.async_.dashboard_views import router as client_router
ninja_api.add_router("/client/", client_router)

# Vendor domain: /api/v1/ninja/vendor/
from apps.vendor.apis.async_.dashboard_views import router as vendor_router
ninja_api.add_router("/vendor/", vendor_router)

# Notification domain: /api/v1/ninja/notifications/
from apps.notification.apis.async_.notification_views import router as notification_async_router
ninja_api.add_router("/notifications/", notification_async_router)

# Support domain: /api/v1/ninja/support/
from apps.support.apis.async_.support_views import router as support_async_router
ninja_api.add_router("/support/", support_async_router)

# Catalog domain: /api/v1/ninja/catalog/
from apps.catalog.apis.async_.catalog_views import router as catalog_async_router
ninja_api.add_router("/catalog/", catalog_async_router)

# Product domain: /api/v1/ninja/products/
from apps.product.apis.async_.product_views import router as product_async_router
ninja_api.add_router("/products/", product_async_router)

# Cart domain: /api/v1/ninja/cart/
from apps.cart.apis.async_.cart_views import router as cart_async_router
ninja_api.add_router("/cart/", cart_async_router)

# Order domain: /api/v1/ninja/orders/
from apps.order.apis.async_.order_views import router as order_async_router
ninja_api.add_router("/orders/", order_async_router)

# Wallet domain: /api/v1/ninja/wallet/
from apps.wallet.apis.async_.wallet_views import router as wallet_async_router
ninja_api.add_router("/wallet/", wallet_async_router)

# Transactions domain: /api/v1/ninja/transactions/
from apps.transactions.apis.async_.transaction_views import router as transaction_async_router
ninja_api.add_router("/transactions/", transaction_async_router)

# Payment domain: /api/v1/ninja/payments/
from apps.payment.apis.async_.payment_views import router as payment_async_router
ninja_api.add_router("/payments/", payment_async_router)

# KYC domain: /api/v1/ninja/kyc/
from apps.kyc.apis.async_.kyc_views import router as kyc_async_router
ninja_api.add_router("/kyc/", kyc_async_router)

# Measurements domain: /api/v1/ninja/measurements/
from apps.measurements.apis.async_.measurement_views import router as measurements_async_router
ninja_api.add_router("/measurements/", measurements_async_router)
