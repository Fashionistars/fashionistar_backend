# apps/admin_backend/urls.py
"""
FASHIONISTAR Admin API — Central URL Registry.

This module is the single, canonical aggregator for ALL admin-facing API
endpoints. Mount this in the project root urls.py under /api/admin/.

Architecture:
  - DRF sync endpoints (POST/PUT/PATCH/DELETE) are included via drf_router
  - Django Ninja async endpoints (GET) are included via ninja_api.urls
  - Each domain's admin_backend/urls.py exports both its DRF patterns AND
    registers its Ninja router here

URL Naming Convention:
  /api/admin/dashboard/      ← KPI aggregator (Ninja async)
  /api/admin/auth/           ← authentication domain
  /api/admin/vendor/         ← vendor domain
  /api/admin/client/         ← client domain
  /api/admin/catalog/        ← catalog domain
  /api/admin/product/        ← product domain
  /api/admin/order/          ← order domain
  /api/admin/custom-order/   ← custom_order domain
  /api/admin/kyc/            ← kyc domain
  /api/admin/wallet/         ← wallet domain
  /api/admin/transactions/   ← transactions domain
  /api/admin/payment/        ← payment domain
  /api/admin/notification/   ← notification domain
  /api/admin/chat/           ← chat domain
  /api/admin/support/        ← support domain
  /api/admin/measurements/   ← measurements domain
  /api/admin/cart/           ← cart domain
  /api/admin/audit/          ← audit_logs domain
  /api/admin/settings/       ← global_platform_settings domain
"""

from __future__ import annotations

from django.urls import path, include
from ninja import NinjaAPI

# ─────────────────────────────────────────────────────────────────────────────
# Central Ninja API instance for ALL admin async read endpoints
# ─────────────────────────────────────────────────────────────────────────────

admin_ninja_api = NinjaAPI(
    title="Fashionistar Admin API",
    version="1.0.0",
    description=(
        "Unified admin API. "
        "GET (read) endpoints are async Django Ninja. "
        "POST/PATCH/DELETE (write) endpoints are DRF sync."
    ),
    urls_namespace="admin_ninja",
    docs_url="/docs/",
)

# ─────────────────────────────────────────────────────────────────────────────
# Register Ninja routers from each app's admin_backend/api.py
# ─────────────────────────────────────────────────────────────────────────────

# Wave A — Dashboard KPI
from apps.admin_backend.dashboard_api import router as dashboard_router
admin_ninja_api.add_router("/dashboard/", dashboard_router)

# Wave B — Identity & Governance
try:
    from apps.authentication.admin_backend.api import router as auth_admin_router
    admin_ninja_api.add_router("/auth/", auth_admin_router)
except ImportError:
    pass

try:
    from apps.vendor.admin_backend.api import router as vendor_admin_router
    admin_ninja_api.add_router("/vendor/", vendor_admin_router)
except ImportError:
    pass

try:
    from apps.client.admin_backend.api import router as client_admin_router
    admin_ninja_api.add_router("/client/", client_admin_router)
except ImportError:
    pass

try:
    from apps.kyc.admin_backend.api import router as kyc_admin_router
    admin_ninja_api.add_router("/kyc/", kyc_admin_router)
except ImportError:
    pass

try:
    from apps.global_platform_settings.admin_backend.api import router as settings_admin_router
    admin_ninja_api.add_router("/settings/", settings_admin_router)
except ImportError:
    pass

try:
    from apps.providers.admin_backend.api import router as providers_admin_router
    admin_ninja_api.add_router("/providers/", providers_admin_router)
except ImportError:
    pass


# Wave C — Commerce Core
try:
    from apps.catalog.admin_backend.api import router as catalog_admin_router
    admin_ninja_api.add_router("/catalog/", catalog_admin_router)
except ImportError:
    pass

try:
    from apps.product.admin_backend.api import router as product_admin_router
    admin_ninja_api.add_router("/product/", product_admin_router)
except ImportError:
    pass

try:
    from apps.order.admin_backend.api import router as order_admin_router
    admin_ninja_api.add_router("/order/", order_admin_router)
except ImportError:
    pass

try:
    from apps.custom_order.admin_backend.api import router as custom_order_admin_router
    admin_ninja_api.add_router("/custom-order/", custom_order_admin_router)
except ImportError:
    pass

try:
    from apps.measurements.admin_backend.api import router as measurements_admin_router
    admin_ninja_api.add_router("/measurements/", measurements_admin_router)
except ImportError:
    pass


# Wave D — Financial Operations
try:
    from apps.wallet.admin_backend.api import router as wallet_admin_router
    admin_ninja_api.add_router("/wallet/", wallet_admin_router)
except ImportError:
    pass

try:
    from apps.transactions.admin_backend.api import router as transactions_admin_router
    admin_ninja_api.add_router("/transactions/", transactions_admin_router)
except ImportError:
    pass

try:
    from apps.payment.admin_backend.api import router as payment_admin_router
    admin_ninja_api.add_router("/payment/", payment_admin_router)
except ImportError:
    pass

# Wave E — Communication & Trust
try:
    from apps.notification.admin_backend.api import router as notification_admin_router
    admin_ninja_api.add_router("/notification/", notification_admin_router)
except ImportError:
    pass

try:
    from apps.chat.admin_backend.api import router as chat_admin_router
    admin_ninja_api.add_router("/chat/", chat_admin_router)
except ImportError:
    pass

try:
    from apps.support.admin_backend.api import router as support_admin_router
    admin_ninja_api.add_router("/support/", support_admin_router)
except ImportError:
    pass

try:
    from apps.audit_logs.admin_backend.api import router as audit_admin_router
    admin_ninja_api.add_router("/audit/", audit_admin_router)
except ImportError:
    pass


# ─────────────────────────────────────────────────────────────────────────────
# DRF sync mutation URL patterns (POST / PATCH / DELETE)
# ─────────────────────────────────────────────────────────────────────────────

drf_urlpatterns = []

# Legacy delivery route preserved
try:
    from .delivery import DeliveryStatusUpdateView
    drf_urlpatterns.append(
        path("delivery/<order_id>/update/", DeliveryStatusUpdateView.as_view(), name="delivery-status-update"),
    )
except ImportError:
    pass

# Wave B — Identity & Governance DRF mutations
try:
    from apps.authentication.admin_backend.urls import urlpatterns as auth_admin_urls
    drf_urlpatterns.append(path("auth/", include((auth_admin_urls, "admin_auth"))))
except ImportError:
    pass

try:
    from apps.vendor.admin_backend.urls import urlpatterns as vendor_admin_urls
    drf_urlpatterns.append(path("vendor/", include((vendor_admin_urls, "admin_vendor"))))
except ImportError:
    pass

try:
    from apps.client.admin_backend.urls import urlpatterns as client_admin_urls
    drf_urlpatterns.append(path("client/", include((client_admin_urls, "admin_client"))))
except ImportError:
    pass

try:
    from apps.kyc.admin_backend.urls import urlpatterns as kyc_admin_urls
    drf_urlpatterns.append(path("kyc/", include((kyc_admin_urls, "admin_kyc"))))
except ImportError:
    pass

try:
    from apps.global_platform_settings.admin_backend.urls import urlpatterns as settings_admin_urls
    drf_urlpatterns.append(path("settings/", include((settings_admin_urls, "admin_settings"))))
except ImportError:
    pass

try:
    from apps.providers.admin_backend.urls import urlpatterns as providers_admin_urls
    drf_urlpatterns.append(path("providers/", include((providers_admin_urls, "admin_providers"))))
except ImportError:
    pass


# Wave C — Commerce Core DRF mutations
try:
    from apps.catalog.admin_backend.urls import urlpatterns as catalog_admin_urls
    drf_urlpatterns.append(path("catalog/", include((catalog_admin_urls, "admin_catalog"))))
except ImportError:
    pass

try:
    from apps.product.admin_backend.urls import urlpatterns as product_admin_urls
    drf_urlpatterns.append(path("product/", include((product_admin_urls, "admin_product"))))
except ImportError:
    pass

try:
    from apps.order.admin_backend.urls import urlpatterns as order_admin_urls
    drf_urlpatterns.append(path("order/", include((order_admin_urls, "admin_order"))))
except ImportError:
    pass

try:
    from apps.custom_order.admin_backend.urls import urlpatterns as custom_order_admin_urls
    drf_urlpatterns.append(path("custom-order/", include((custom_order_admin_urls, "admin_custom_order"))))
except ImportError:
    pass

try:
    from apps.measurements.admin_backend.urls import urlpatterns as measurements_admin_urls
    drf_urlpatterns.append(path("measurements/", include((measurements_admin_urls, "admin_measurements"))))
except ImportError:
    pass


# Wave D — Financial Operations DRF mutations
try:
    from apps.wallet.admin_backend.urls import urlpatterns as wallet_admin_urls
    drf_urlpatterns.append(path("wallet/", include((wallet_admin_urls, "admin_wallet"))))
except ImportError:
    pass

try:
    from apps.transactions.admin_backend.urls import urlpatterns as transactions_admin_urls
    drf_urlpatterns.append(path("transactions/", include((transactions_admin_urls, "admin_transactions"))))
except ImportError:
    pass

try:
    from apps.payment.admin_backend.urls import urlpatterns as payment_admin_urls
    drf_urlpatterns.append(path("payment/", include((payment_admin_urls, "admin_payment"))))
except ImportError:
    pass

# Wave E — Communication & Trust DRF mutations
try:
    from apps.notification.admin_backend.urls import urlpatterns as notification_admin_urls
    drf_urlpatterns.append(path("notification/", include((notification_admin_urls, "admin_notification"))))
except ImportError:
    pass

try:
    from apps.chat.admin_backend.urls import urlpatterns as chat_admin_urls
    drf_urlpatterns.append(path("chat/", include((chat_admin_urls, "admin_chat"))))
except ImportError:
    pass

try:
    from apps.support.admin_backend.urls import urlpatterns as support_admin_urls
    drf_urlpatterns.append(path("support/", include((support_admin_urls, "admin_support"))))
except ImportError:
    pass

try:
    from apps.audit_logs.admin_backend.urls import urlpatterns as audit_admin_urls
    drf_urlpatterns.append(path("audit/", include((audit_admin_urls, "admin_audit"))))
except ImportError:
    pass


# ─────────────────────────────────────────────────────────────────────────────
# Combined urlpatterns — DRF sync writes + Ninja async reads
# ─────────────────────────────────────────────────────────────────────────────

app_name = "admin_backend"

urlpatterns = drf_urlpatterns + [
    # Django Ninja async reads (all GET endpoints)
    path("", admin_ninja_api.urls),
]
