# apps/vendor/admin_backend/urls.py
"""DRF URL patterns for the vendor admin domain."""
from django.urls import path
from .views import (
    AdminVendorApproveView, AdminVendorSuspendView,
    AdminVendorReactivateView, AdminVendorRejectView,
    AdminVendorCommissionView, AdminVendorFeaturedView,
)

urlpatterns = [
    path("<str:vendor_id>/approve/", AdminVendorApproveView.as_view(), name="admin-vendor-approve"),
    path("<str:vendor_id>/suspend/", AdminVendorSuspendView.as_view(), name="admin-vendor-suspend"),
    path("<str:vendor_id>/reactivate/", AdminVendorReactivateView.as_view(), name="admin-vendor-reactivate"),
    path("<str:vendor_id>/reject/", AdminVendorRejectView.as_view(), name="admin-vendor-reject"),
    path("<str:vendor_id>/commission/", AdminVendorCommissionView.as_view(), name="admin-vendor-commission"),
    path("<str:vendor_id>/featured/", AdminVendorFeaturedView.as_view(), name="admin-vendor-featured"),
]
