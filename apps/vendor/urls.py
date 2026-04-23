# apps/vendor/urls.py
"""
Vendor Domain — DRF URL Patterns.
Mounted at: /api/v1/vendor/

Endpoints — Profile & Setup:
  GET    /api/v1/vendor/profile/               — retrieve store profile
  PATCH  /api/v1/vendor/profile/               — update profile (includes collections M2M)
  GET    /api/v1/vendor/setup/                 — get onboarding setup state
  POST   /api/v1/vendor/setup/                 — first-time vendor setup (provision)
  POST   /api/v1/vendor/payout/                — save bank / payout details
  POST   /api/v1/vendor/pin/set/               — set 4-digit payout confirmation PIN
  POST   /api/v1/vendor/pin/verify/            — verify PIN before payout/transfer

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

from apps.vendor.apis.sync.analytics_views import (
    VendorAnalyticsSummaryView,
    VendorCouponListView,
    VendorCustomerBehaviorView,
    VendorEarningTrackerView,
    VendorLowStockView,
    VendorMonthlyOrderChart,
    VendorMonthlyProductChart,
    VendorOrderDetailView,
    VendorOrderListView,
    VendorOrderStatusCountsView,
    VendorPaymentDistributionView,
    VendorRevenueChart,
    VendorReviewDetailView,
    VendorReviewListView,
    VendorTopCategoriesView,
    VendorTopSellingProductsView,
    VendorProductListView,
)
from apps.vendor.apis.sync.profile_views import (
    VendorPayoutView,
    VendorProfileView,
    VendorSetupStateView,
    VendorSetPinView,
    VendorVerifyPinView,
)

app_name = "vendor"

urlpatterns = [
    # ── Profile & Onboarding ─────────────────────────────────────
    path("profile/",     VendorProfileView.as_view(),    name="profile"),
    path("setup/",       VendorSetupStateView.as_view(), name="setup-state"),
    path("payout/",      VendorPayoutView.as_view(),     name="payout"),
    path("pin/set/",     VendorSetPinView.as_view(),     name="pin-set"),
    path("pin/verify/",  VendorVerifyPinView.as_view(),  name="pin-verify"),

    # ── Analytics ─────────────────────────────────────────────────
    path("analytics/",               VendorAnalyticsSummaryView.as_view(),   name="analytics"),
    path("analytics/revenue/",       VendorRevenueChart.as_view(),           name="analytics-revenue"),
    path("analytics/orders/",        VendorMonthlyOrderChart.as_view(),      name="analytics-orders"),
    path("analytics/products/",      VendorMonthlyProductChart.as_view(),    name="analytics-products"),
    path("analytics/customers/",     VendorCustomerBehaviorView.as_view(),   name="analytics-customers"),
    path("analytics/categories/",    VendorTopCategoriesView.as_view(),      name="analytics-categories"),
    path("analytics/distribution/",  VendorPaymentDistributionView.as_view(), name="analytics-distribution"),

    # ── Products ─────────────────────────────────────────────────
    path("products/",           VendorProductListView.as_view(),        name="products"),
    path("products/low-stock/", VendorLowStockView.as_view(),           name="products-low-stock"),
    path("products/top/",       VendorTopSellingProductsView.as_view(), name="products-top"),

    # ── Orders ───────────────────────────────────────────────────
    path("orders/",                    VendorOrderListView.as_view(),          name="orders"),
    path("orders/status-counts/",      VendorOrderStatusCountsView.as_view(),  name="orders-status-counts"),
    path("orders/<int:order_id>/",     VendorOrderDetailView.as_view(),        name="order-detail"),

    # ── Earnings ─────────────────────────────────────────────────
    path("earnings/",  VendorEarningTrackerView.as_view(), name="earnings"),

    # ── Reviews ──────────────────────────────────────────────────
    path("reviews/",                    VendorReviewListView.as_view(),   name="reviews"),
    path("reviews/<int:review_id>/",    VendorReviewDetailView.as_view(), name="review-detail"),

    # ── Coupons ──────────────────────────────────────────────────
    path("coupons/",  VendorCouponListView.as_view(), name="coupons"),
]
