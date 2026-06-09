# apps/vendor/urls.py
"""
Vendor Domain — DRF URL Patterns.
Mounted at: /api/v1/vendor/

Endpoints — Profile & Setup:
  GET    /api/v1/vendor/profile/               — retrieve store profile
  PATCH  /api/v1/vendor/profile/               — update profile (includes collections M2M)
  GET    /api/v1/vendor/setup/                 — get onboarding setup state
  POST   /api/v1/vendor/setup/                 — first-time vendor setup (provision)
  POST   /api/v1/vendor/payout/                — save bank / payout details (legacy OneToOne)
  POST   /api/v1/vendor/pin/set/               — set 4-digit payout confirmation PIN
  POST   /api/v1/vendor/pin/verify/            — verify PIN before payout/transfer

Endpoints — Bank Accounts (Multi-Account Payout Gate):
  GET    /api/v1/vendor/bank-accounts/                    — list saved bank accounts (max 5)
  POST   /api/v1/vendor/bank-accounts/                    — create & register bank account
  POST   /api/v1/vendor/bank-accounts/resolve/            — resolve account name via Paystack
  DELETE /api/v1/vendor/bank-accounts/<uuid:pk>/          — delete a saved bank account
  PATCH  /api/v1/vendor/bank-accounts/<uuid:pk>/default/  — set as default account

Endpoints — Payout Request:
  POST   /api/v1/vendor/payout/request/        — request payout to a saved bank account

Endpoints — Analytics:
  GET    /api/v1/vendor/analytics/             — full analytics snapshot
  GET    /api/v1/vendor/analytics/revenue/     — monthly revenue chart (6mo)
  GET    /api/v1/vendor/analytics/orders/      — monthly order chart
  GET    /api/v1/vendor/analytics/products/    — monthly products chart
  GET    /api/v1/vendor/analytics/customers/   — customer behaviour
  GET    /api/v1/vendor/analytics/categories/  — top performing categories
  GET    /api/v1/vendor/analytics/distribution/— payment method distribution

Endpoints — Products:
  GET    /api/v1/vendor/products/              — vendor's own product list
  GET    /api/v1/vendor/products/low-stock/    — products below stock threshold
  GET    /api/v1/vendor/products/top/          — top selling products

Endpoints — Orders:
  GET    /api/v1/vendor/orders/                — vendor's order list
  GET    /api/v1/vendor/orders/status-counts/  — order count by status
  GET    /api/v1/vendor/orders/<int:order_id>/ — single order detail

Endpoints — Earnings:
  GET    /api/v1/vendor/earnings/              — comprehensive earning tracker

Endpoints — Reviews:
  GET    /api/v1/vendor/reviews/               — reviews on vendor products
  GET    /api/v1/vendor/reviews/<int:review_id>/ — single review detail

Endpoints — Coupons:
  GET    /api/v1/vendor/coupons/               — vendor's coupon list

Async endpoints (Ninja) are mounted via the Ninja router in backend/ninja_api.py
at prefix: /api/v1/ninja/vendor/
"""
from django.urls import path

from apps.vendor.apis.sync.product_views import (
    VendorOrderStatusUpdateView,
    VendorProductCreateView,
    VendorProductDeleteView,
    VendorProductFilterView,
    VendorProductUpdateView,
)
from apps.vendor.apis.sync.profile_views import (
    VendorPayoutView,
    VendorProfileView,
    VendorSetupStateView,
    VendorSetPinView,
    VendorVerifyPinView,
    PublicVendorListView,
    PublicVendorDetailView,
)
from apps.vendor.apis.sync.bank_account_views import (
    VendorBankAccountResolveView,
    VendorBankAccountListCreateView,
    VendorBankAccountDeleteView,
    VendorBankAccountSetDefaultView,
)
from apps.vendor.apis.sync.payout_request_views import VendorPayoutRequestView

app_name = "vendor_domain"

urlpatterns = [
    # ── Profile & Onboarding ─────────────────────────────────────
    path("profile/",     VendorProfileView.as_view(),    name="profile"),
    path("setup/",       VendorSetupStateView.as_view(), name="setup-state"),
    path("payout/",      VendorPayoutView.as_view(),     name="payout"),       # legacy OneToOne
    path("pin/set/",     VendorSetPinView.as_view(),     name="pin-set"),
    path("pin/verify/",  VendorVerifyPinView.as_view(),  name="pin-verify"),

    # ── Bank Accounts (Multi-Account Payout Gate) ─────────────────
    path("bank-accounts/resolve/",              VendorBankAccountResolveView.as_view(),    name="bank-accounts-resolve"),
    path("bank-accounts/",                      VendorBankAccountListCreateView.as_view(), name="bank-accounts"),
    path("bank-accounts/<uuid:pk>/",            VendorBankAccountDeleteView.as_view(),     name="bank-account-delete"),
    path("bank-accounts/<uuid:pk>/default/",    VendorBankAccountSetDefaultView.as_view(), name="bank-account-set-default"),

    # ── Payout Request ────────────────────────────────────────────
    path("payout/request/",  VendorPayoutRequestView.as_view(), name="payout-request"),

    # ── Public (AllowAny) ─────────────────────────────────────────
    path("public/",             PublicVendorListView.as_view(),         name="public-list"),
    path("public/<slug:store_slug>/", PublicVendorDetailView.as_view(), name="public-detail"),

    # ── Products Mutations ─────────────────────────────────────────
    path("products/create/",                   VendorProductCreateView.as_view(),      name="product-create"),
    path("products/filter/",                   VendorProductFilterView.as_view(),      name="product-filter"),
    path("products/<str:product_pid>/edit/",   VendorProductUpdateView.as_view(),      name="product-edit"),
    path("products/<str:product_pid>/delete/", VendorProductDeleteView.as_view(),      name="product-delete"),

    # ── Orders Mutations ───────────────────────────────────────────
    path("orders/<int:order_id>/status/",       VendorOrderStatusUpdateView.as_view(),  name="order-status-update"),
]
