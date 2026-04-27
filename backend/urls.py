from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from backend.ninja_api import ninja_api

# ── Custom error handlers (JSON for API, HTML for browser) ──────────────────
handler400 = "backend.error_views.bad_request_handler"
handler403 = "backend.error_views.forbidden_handler"
handler404 = "backend.error_views.not_found_handler"
handler500 = "backend.error_views.server_error_handler"


# drf-yasg: OpenAPI/Swagger schema generation
from apps.common.views import HealthCheckView
from rest_framework import permissions
from drf_yasg.views import get_schema_view
from drf_yasg import openapi

api_info = openapi.Info(
    title="FASHIONISTAR E-commerce Backend APIs",
    default_version="v1",
    description="API documentation for FASHIONISTAR E-commerce Backend",
    terms_of_service="https://www.google.com/policies/terms/",
    contact=openapi.Contact(email="fashionistarclothings@outlook.com"),
    license=openapi.License(name="BSD License"),
)

# ── Schema view ─────────────────────────────────────────────────────────────
# cache_class uses 'schema' LocMemCache (settings.CACHES['schema']) so the
# Swagger UI homepage does NOT touch Redis. Redis downtime in dev/staging
# will never cause a 500 on GET /.
schema_view = get_schema_view(
    api_info,
    public=True,
    permission_classes=(permissions.AllowAny,),
)


def health_check(request):
    """Kubernetes readiness/liveness probe endpoint."""
    from django.db import connection

    try:
        connection.ensure_connection()
        db_ok = True
    except Exception:
        db_ok = False
    from django.http import JsonResponse

    return JsonResponse(
        {
            "status": "ok" if db_ok else "degraded",
            "service": "fashionistar-api",
            "version": "v1",
            "database": "ok" if db_ok else "error",
        },
        status=200 if db_ok else 503,
    )


urlpatterns = [
    path("health/", health_check, name="health"),
    path(
        "swagger<format>/", schema_view.without_ui(cache_timeout=0), name="schema-json"
    ),
    path("", schema_view.with_ui("swagger", cache_timeout=0), name="schema-swagger-ui"),
    path("redoc/", schema_view.with_ui("redoc", cache_timeout=0), name="schema-redoc"),
    # ── Health Check ─────────────────────────────────────────────────────────
    # GET /api/v1/health/
    # Used by: AWS ELB, Render.com, Kubernetes probes, Uptime Robot
    path("v1/health/", HealthCheckView.as_view(), name="health-check"),
    # Admin URL
    path("admin/", admin.site.urls),
    # ── New Modular Monolith (v1) ──────────────────────────────────────────
    path("api/", include("apps.authentication.urls", namespace="authentication")),
    # ── Common Utilities (health check, Cloudinary presign, Cloudinary webhook, metrics, etc.) ────────────────────────
    path("api/", include("apps.common.urls", namespace="common")),
    # ── Phase 2: Client Domain (DRF sync) ─────────────────────────────────────
    path("api/v1/client/", include("apps.client.urls", namespace="client")),
    # ── Phase 2: Vendor Domain (DRF sync) ─────────────────────────────────────
    path("api/v1/vendor/", include("apps.vendor.urls", namespace="vendor_domain")),
    # ── Financial Domains: wallet custody, internal ledger, provider payments ─
    path("api/v1/wallet/", include("apps.wallet.urls", namespace="wallet")),
    path("api/v1/transactions/", include("apps.transactions.urls", namespace="transactions")),
    path("api/v1/payment/", include("apps.payment.urls", namespace="payment")),
    # ── Canonical Catalog Domain: category, brand, collection, discovery metadata ─
    path("api/v1/catalog/", include("apps.catalog.urls", namespace="catalog")),
    # ── Phase 4: Product Catalogue Domain ──────────────────────────────────────
    path("api/v1/products/", include("apps.product.urls", namespace="product")),
    # ── Phase 4: Shopping Cart Domain ──────────────────────────────────────────
    path("api/v1/cart/", include("apps.cart.urls", namespace="cart")),
    # ── Phase 4: Order Lifecycle Domain ───────────────────────────────────────
    path("api/v1/orders/", include("apps.order.urls", namespace="order")),
    # ── Phase 2: Central Async Ninja API (/api/v1/ninja/*) ───────────────────
    path("api/v1/ninja/", ninja_api.urls),
    path("admin_backend/", include("apps.admin_backend.urls")),
]


# ====================================================================================

# ====================================================================================
# *** EDIT 3: CONDITIONAL STATIC FILE SERVING ***
# - Serving media files is fine, though in prod, Cloudinary handles it fully.
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
# urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)


# - STATIC files MUST only be served by the Django development server when DEBUG=True.
# - When DEBUG=False, Cloudinary/STATICFILES_STORAGE handles it, so this block is not run.
if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
# ====================================================================================
