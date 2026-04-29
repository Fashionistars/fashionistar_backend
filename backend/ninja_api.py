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
            # Ninja read handlers can use request.auth.client_profile /
            # request.auth.vendor_profile without issuing another profile query.
            user = await (
                UnifiedUser.objects.select_related("client_profile", "vendor_profile")
                .aget(pk=user_id, is_active=True)
            )
            return user

        except Exception:
            return None


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
