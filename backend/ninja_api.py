# backend/ninja_api.py
"""
Fashionistar — Central Django-Ninja API (Async).

Architecture:
    All high-performance async endpoints are registered here as a SINGLE
    NinjaAPI instance.  Never instantiate NinjaAPI anywhere else in the
    project — import this module's `ninja_api` object.

Mounted at:
    /api/v1/ninja/         (see backend/urls.py)

Authentication:
    All routes use JWT Bearer (AsyncJWTAuth) by default.
    Public endpoints explicitly override with auth=None.

Router registry  ← SINGLE source-of-truth:
    /api/v1/ninja/common/          → apps/common
    /api/v1/ninja/client/          → apps/client
    /api/v1/ninja/vendor/          → apps/vendor
    /api/v1/ninja/notifications/   → apps/notification
    /api/v1/ninja/support/         → apps/support
    /api/v1/ninja/catalog/         → apps/catalog
    /api/v1/ninja/products/        → apps/product
    /api/v1/ninja/cart/            → apps/cart
    /api/v1/ninja/orders/                    → apps/order
    /api/v1/ninja/wallet/                    → apps/wallet (GET: dashboard, balance)
    /api/v1/ninja/wallet/company/payout/     → apps/wallet (POST: company commission payout)
    /api/v1/ninja/transactions/              → apps/transactions
    /api/v1/ninja/payments/                  → apps/payment
    /api/v1/ninja/kyc/                       → apps/kyc
    /api/v1/ninja/measurements/              → apps/measurements
    /api/v1/ninja/client/custom-orders/      → apps/apps/custom-orders (custom_order_views)
    /api/v1/ninja/vendor/custom-orders/      → apps/apps/custom-orders (custom_order_views)
"""
import logging

from ninja import NinjaAPI
from ninja.security import HttpBearer

logger = logging.getLogger("application")


# ── JWT Bearer Authentication ─────────────────────────────────────────────────

class AsyncJWTAuth(HttpBearer):
    """
    JWT Bearer authentication for Ninja endpoints.

    Validates the same SimpleJWT access token used by DRF.
    Returns the UnifiedUser instance so `request.auth` is the user object,
    with client_profile, vendor_profile, and kyc_submission pre-fetched.
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
            # Async ORM lookup. Reverse OneToOne prefetch related profiles are hydrated here so
            # Ninja Async read downstream handlers can acces use request.auth.client_profile,
            # request.auth.vendor_profile, and request.auth.kyc_submission
            # without issuing another extra profile/KYC queries.
            return await (
                UnifiedUser.objects.select_related(
                    "client_profile",
                    "vendor_profile",
                    "kyc_submission",
                )
                .aget(pk=user_id, is_active=True)
            )
        except Exception as exc:
            logger.warning(" ninja_api.AsyncJWTAuth: failed to validate token: %s", exc)
            return None


# ── Central Ninja API (singleton) ─────────────────────────────────────────────
#
#  All Ninja endpoints MUST be mounted under /api/v1/ninja/ to:
#    1. Maintain uniform v1 versioning across the whole API surface.
#    2. Avoid URL collisions with DRF sync endpoints at /api/v1/<domain>/.
#    3. Make the async/sync split explicit for clients:
#          Reads  → Ninja  /api/v1/ninja/*
#          Writes → DRF    /api/v1/*

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


# ── Domain Router Registry ────────────────────────────────────────────────────
# One add_router call per domain — guard with try/except so a missing
# optional router never crashes the other 13 domains.

# Common reference-data domain: /api/v1/ninja/common/
try:
    from apps.common.apis.async_.reference_views import router as common_router
    ninja_api.add_router("/common/", common_router)
    logger.info("✅ NinjaAPI: common router registered at /api/v1/ninja/common/")
except Exception as exc:  # pragma: no cover
    logger.warning("ℹ️ NinjaAPI: common router FAILED to register: %s", exc)


# Telemetry domain: /api/v1/ninja/common/telemetry/
# Receives Core Web Vitals from Next.js edge; auth via X-Internal-Token header.
try:
    from apps.common.telemetry_api import telemetry_router
    ninja_api.add_router("/common/telemetry/", telemetry_router, url_name_prefix="telemetry")
    logger.info("✅ NinjaAPI: telemetry router registered at /api/v1/ninja/common/telemetry/")
except Exception as exc:  # pragma: no cover
    logger.warning("ℹ️ NinjaAPI: telemetry router FAILED to register: %s", exc)



# Client domain: /api/v1/ninja/client/
try:
    from apps.client.apis.async_.dashboard_views import router as client_router
    ninja_api.add_router("/client/", client_router)
    logger.info("✅ NinjaAPI: client router registered at /api/v1/ninja/client/")
except Exception as exc:  # pragma: no cover
    logger.warning("ℹ️ NinjaAPI: client router FAILED to register: %s", exc)


# Vendor domain: /api/v1/ninja/vendor/
try:
    from apps.vendor.apis.async_.dashboard_views import router as vendor_router
    ninja_api.add_router("/vendor/", vendor_router)
    logger.info("✅ NinjaAPI: vendor router registered at /api/v1/ninja/vendor/")
except Exception as exc:  # pragma: no cover
    logger.warning("ℹ️ NinjaAPI: vendor router FAILED to register: %s", exc)


# Notification domain: /api/v1/ninja/notifications/
try:
    from apps.notification.apis.async_.notification_views import router as notification_router
    ninja_api.add_router("/notifications/", notification_router)
    logger.info("✅ NinjaAPI: notification router registered at /api/v1/ninja/notifications/")
except Exception as exc:  # pragma: no cover
    logger.warning("ℹ️ NinjaAPI: notification router FAILED to register: %s", exc)


# Support domain: /api/v1/ninja/support/
try:
    from apps.support.apis.async_.support_views import router as support_router
    ninja_api.add_router("/support/", support_router)
    logger.info("✅ NinjaAPI: support router registered at /api/v1/ninja/support/")
except Exception as exc:  # pragma: no cover
    logger.warning("ℹ️ NinjaAPI: support router FAILED to register: %s", exc)


# Catalog domain: /api/v1/ninja/catalog/
try:
    from apps.catalog.apis.async_.catalog_views import router as catalog_router
    ninja_api.add_router("/catalog/", catalog_router)
    logger.info("✅ NinjaAPI: catalog router registered at /api/v1/ninja/catalog/")
except Exception as exc:  # pragma: no cover
    logger.warning("ℹ️ NinjaAPI: catalog router FAILED to register: %s", exc)


# Product domain: /api/v1/ninja/products/ and /api/v1/ninja/product/
try:
    from apps.product.apis.async_.product_views import router as product_router
    ninja_api.add_router("/products/", product_router, url_name_prefix="products")
    ninja_api.add_router("/product/", product_router, url_name_prefix="product")
    logger.info("✅ NinjaAPI: product router registered at /api/v1/ninja/products/ and /api/v1/ninja/product/")
except Exception as exc:  # pragma: no cover
    logger.warning("ℹ️ NinjaAPI: product router FAILED to register: %s", exc)




# Order domain: /api/v1/ninja/orders/
try:
    from apps.order.apis.async_.order_views import router as order_router
    ninja_api.add_router("/orders/", order_router)
    logger.info("✅ NinjaAPI: order router registered at /api/v1/ninja/orders/")
except Exception as exc:  # pragma: no cover
    logger.warning("ℹ️ NinjaAPI: order router FAILED to register: %s", exc)


# Wallet domain: /api/v1/ninja/wallet/
# Read-only dashboard + balance endpoints.
try:
    from apps.wallet.apis.async_.wallet_views import router as wallet_router
    ninja_api.add_router("/wallet/", wallet_router)
    logger.info("✅ NinjaAPI: wallet router registered at /api/v1/ninja/wallet/")
except Exception as exc:  # pragma: no cover
    logger.warning("ℹ️ NinjaAPI: wallet router FAILED to register: %s", exc)


# Wallet Mutations: /api/v1/ninja/wallet/
# High-security write endpoints — company commission payout (Double-Door secured).
try:
    from apps.wallet.apis.async_.mutation_views import router as wallet_mutation_router
    ninja_api.add_router("/wallet/", wallet_mutation_router)
    logger.info("✅ NinjaAPI: wallet mutation router registered (POST /api/v1/ninja/wallet/company/payout/)")
except Exception as exc:  # pragma: no cover
    logger.warning("ℹ️ NinjaAPI: wallet mutation router FAILED to register: %s", exc)


# Transactions domain: /api/v1/ninja/transactions/
try:
    from apps.transactions.apis.async_.transaction_views import router as transaction_router
    ninja_api.add_router("/transactions/", transaction_router)
    logger.info("✅ NinjaAPI: transactions router registered at /api/v1/ninja/transactions/")
except Exception as exc:  # pragma: no cover
    logger.warning("ℹ️ NinjaAPI: transactions router FAILED to register: %s", exc)


# Payment domain: /api/v1/ninja/payments/
try:
    from apps.payment.apis.async_.payment_views import router as payment_router
    ninja_api.add_router("/payments/", payment_router)
    logger.info("✅ NinjaAPI: payment router registered at /api/v1/ninja/payments/")
except Exception as exc:  # pragma: no cover
    logger.warning("ℹ️ NinjaAPI: payment router FAILED to register: %s", exc)


# KYC domain: /api/v1/ninja/kyc/
try:
    from apps.kyc.apis.async_.kyc_views import router as kyc_router
    ninja_api.add_router("/kyc/", kyc_router)
    logger.info("✅ NinjaAPI: kyc router registered at /api/v1/ninja/kyc/")
except Exception as exc:  # pragma: no cover
    logger.warning("ℹ️ NinjaAPI: kyc router FAILED to register: %s", exc)


# Measurements domain: /api/v1/ninja/measurements/
try:
    from apps.measurements.apis.async_.measurement_views import router as measurements_router
    ninja_api.add_router("/measurements/", measurements_router)
    logger.info("✅ NinjaAPI: measurements router registered at /api/v1/ninja/measurements/")
except Exception as exc:  # pragma: no cover
    logger.warning("ℹ️ NinjaAPI: measurements router FAILED to register: %s", exc)


# Custom Order (Client) domain: /api/v1/ninja/client/custom-orders/
try:
    from apps.custom_order.apis.custom_order_views import client_custom_order_router
    ninja_api.add_router("/client/custom-orders/", client_custom_order_router)
    logger.info("✅ NinjaAPI: client custom-orders router registered at /api/v1/ninja/client/custom-orders/")
except Exception as exc:  # pragma: no cover
    logger.warning("ℹ️ NinjaAPI: client custom-orders router FAILED to register: %s", exc)


# Custom Order (Vendor) domain: /api/v1/ninja/vendor/custom-orders/
try:
    from apps.custom_order.apis.custom_order_views import vendor_custom_order_router
    ninja_api.add_router("/vendor/custom-orders/", vendor_custom_order_router)
    logger.info("✅ NinjaAPI: vendor custom-orders router registered at /api/v1/ninja/vendor/custom-orders/")
except Exception as exc:  # pragma: no cover
    logger.warning("ℹ️ NinjaAPI: vendor custom-orders router FAILED to register: %s", exc)
