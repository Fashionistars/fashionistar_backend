# apps/vendor/urls.py
"""
Vendor Domain — DRF URL Patterns.
Mounted at: /api/v1/vendor/

Endpoints — Profile & Setup:
  PATCH  /api/v1/vendor/profile/               — update profile (includes collections M2M)
  POST   /api/v1/vendor/setup/                 — first-time vendor setup (provision)
  POST   /api/v1/vendor/payout/                — save bank / payout details (legacy OneToOne)
  POST   /api/v1/vendor/pin/set/               — set 4-digit payout confirmation PIN
  POST   /api/v1/vendor/pin/verify/            — verify PIN before payout/transfer

Endpoints — Bank Accounts (Multi-Account Payout Gate):
  POST   /api/v1/vendor/bank-accounts/                    — create & register bank account
  POST   /api/v1/vendor/bank-accounts/resolve/            — resolve account name via Paystack
  DELETE /api/v1/vendor/bank-accounts/<uuid:pk>/          — delete a saved bank account
  PATCH  /api/v1/vendor/bank-accounts/<uuid:pk>/default/  — set as default account

Endpoints — Payout Request:
  POST   /api/v1/vendor/payout/request/        — request payout to a saved bank account


Endpoints — Reviews:
  GET    /api/v1/vendor/reviews/               — reviews on vendor products
  GET    /api/v1/vendor/reviews/<int:review_id>/ — single review detail

Async endpoints (Ninja) are mounted via the Ninja router in backend/ninja_api.py
at prefix: /api/v1/ninja/vendor/
"""
from django.urls import path

from apps.vendor.apis.sync.product_views import (
    VendorOrderStatusUpdateView,
)
from apps.product.apis.sync.product_views import (
    VendorProductListCreateView,
    VendorProductDetailView,
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
    path("products/create/",                   VendorProductListCreateView.as_view(),  name="product-create"),
    path("products/filter/",                   VendorProductListCreateView.as_view(),  name="product-filter"),
    path("products/<slug:slug>/edit/",         VendorProductDetailView.as_view(),      name="product-edit"),
    path("products/<slug:slug>/delete/",       VendorProductDetailView.as_view(),      name="product-delete"),

    # ── Orders Mutations ───────────────────────────────────────────
    path("orders/<int:order_id>/status/",       VendorOrderStatusUpdateView.as_view(),  name="order-status-update"),
]
