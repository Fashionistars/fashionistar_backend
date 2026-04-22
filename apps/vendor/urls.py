# apps/vendor/urls.py
"""
Vendor Domain — DRF URL Patterns.
Mounted at: /api/v1/vendor/
"""
from django.urls import path

from apps.vendor.apis.sync.profile_views import (
    VendorPayoutView,
    VendorProfileView,
    VendorSetupStateView,
)

app_name = "vendor"

urlpatterns = [
    path("profile/", VendorProfileView.as_view(),    name="profile"),
    path("setup/",   VendorSetupStateView.as_view(), name="setup-state"),
    path("payout/",  VendorPayoutView.as_view(),     name="payout"),
]
