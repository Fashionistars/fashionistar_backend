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

            # Async ORM lookup
            user = await UnifiedUser.objects.aget(pk=user_id, is_active=True)
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

# Client domain: /api/v1/ninja/client/
from apps.client.apis.async_.dashboard_views import router as client_router
ninja_api.add_router("/client/", client_router)

# Vendor domain: /api/v1/ninja/vendor/
from apps.vendor.apis.async_.dashboard_views import router as vendor_router
ninja_api.add_router("/vendor/", vendor_router)
