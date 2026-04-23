# apps/vendor/urls.py
"""
Vendor Domain — DRF URL Patterns.
Mounted at: /api/v1/vendor/

Endpoints:
  GET  /api/v1/vendor/profile/       — retrieve store profile
  PATCH /api/v1/vendor/profile/      — update profile (includes collections M2M)
  GET  /api/v1/vendor/setup/         — get onboarding setup state
  POST /api/v1/vendor/setup/         — first-time vendor setup (provision)
  POST /api/v1/vendor/payout/        — save bank / payout details
  POST /api/v1/vendor/pin/set/       — set 4-digit payout confirmation PIN
  POST /api/v1/vendor/pin/verify/    — verify PIN before payout/transfer

Async endpoints (Ninja) are mounted via the Ninja router in backend/ninja_api.py
at prefix: /api/v1/ninja/vendor/
"""
from django.urls import path

from apps.vendor.apis.sync.profile_views import (
    VendorPayoutView,
    VendorProfileView,
    VendorSetupStateView,
    VendorSetPinView,
    VendorVerifyPinView,
)

app_name = "vendor"

urlpatterns = [
    path("profile/",    VendorProfileView.as_view(),    name="profile"),
    path("setup/",      VendorSetupStateView.as_view(), name="setup-state"),
    path("payout/",     VendorPayoutView.as_view(),     name="payout"),
    path("pin/set/",    VendorSetPinView.as_view(),     name="pin-set"),
    path("pin/verify/", VendorVerifyPinView.as_view(),  name="pin-verify"),
]
