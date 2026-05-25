"""Focused vendor backend contract tests for auth guards and selectors."""

from __future__ import annotations

import pytest
from rest_framework.permissions import IsAuthenticated
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.authentication.models import UnifiedUser
from apps.common.permissions import IsVendor
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
    VendorProductListView,
    VendorRevenueChart,
    VendorReviewDetailView,
    VendorReviewListView,
    VendorTopCategoriesView,
    VendorTopSellingProductsView,
)
from apps.vendor.models import VendorPayoutProfile, VendorProfile, VendorSetupState
from apps.vendor.services.vendor_service import VendorService


def _create_user(email: str, role: str) -> UnifiedUser:
    return UnifiedUser.objects.create_user(
        email=email,
        password="Password123!",
        role=role,
        is_active=True,
        is_verified=True,
    )


def _auth_client(user: UnifiedUser) -> APIClient:
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(user).access_token}")
    return client


@pytest.mark.django_db
def test_vendor_service_get_profile_selects_canonical_setup_and_payout_relations():
    user = _create_user("vendor.service.contract@fashionistar.test", UnifiedUser.ROLE_VENDOR)
    profile = VendorProfile.objects.create(user=user, store_name="Contract Atelier")
    VendorSetupState.objects.create(vendor=profile, profile_complete=True, current_step=2)
    VendorPayoutProfile.objects.create(
        vendor=profile,
        bank_name="Contract Bank",
        account_name="Contract Atelier",
        account_number_enc=b"encrypted-account",
        account_last4="1234",
    )

    loaded_profile = VendorService.get_profile(user)

    assert loaded_profile.pk == profile.pk
    assert loaded_profile.vendor_setup_state.current_step == 2
    assert loaded_profile.vendor_payout_profile.account_last4 == "1234"


@pytest.mark.parametrize(
    "view_cls",
    [
        VendorAnalyticsSummaryView,
        VendorRevenueChart,
        VendorMonthlyOrderChart,
        VendorMonthlyProductChart,
        VendorEarningTrackerView,
        VendorCustomerBehaviorView,
        VendorTopCategoriesView,
        VendorPaymentDistributionView,
        VendorProductListView,
        VendorLowStockView,
        VendorTopSellingProductsView,
        VendorOrderListView,
        VendorOrderDetailView,
        VendorOrderStatusCountsView,
        VendorReviewListView,
        VendorReviewDetailView,
        VendorCouponListView,
    ],
)
def test_vendor_sync_analytics_and_list_views_require_vendor_auth(view_cls):
    assert view_cls.permission_classes == [IsAuthenticated, IsVendor]


@pytest.mark.django_db
def test_vendor_sync_endpoint_rejects_client_token_before_profile_lookup():
    client_user = _create_user("client.vendor.blocked@fashionistar.test", UnifiedUser.ROLE_CLIENT)

    response = _auth_client(client_user).get("/api/v1/vendor/products/")

    assert response.status_code == 403
