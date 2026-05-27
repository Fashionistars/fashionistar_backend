# apps/kyc/admin_backend/urls.py
"""DRF URL patterns for KYC admin domain."""
from django.urls import path
from .views import AdminKYCApproveView, AdminKYCRejectView, AdminKYCInReviewView

urlpatterns = [
    path("<str:submission_id>/approve/", AdminKYCApproveView.as_view(), name="admin-kyc-approve"),
    path("<str:submission_id>/reject/", AdminKYCRejectView.as_view(), name="admin-kyc-reject"),
    path("<str:submission_id>/in-review/", AdminKYCInReviewView.as_view(), name="admin-kyc-in-review"),
]
