"""Focused tests for vendor async Ninja read endpoints."""

from __future__ import annotations

import pytest
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.authentication.models import UnifiedUser
from apps.vendor.models import VendorProfile, VendorSetupState


def _auth_client(user: UnifiedUser) -> APIClient:
    """Return an API client authenticated with a SimpleJWT access token."""

    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(user).access_token}")
    return client


@pytest.mark.django_db
def test_vendor_ninja_profile_and_setup_reads():
    """Vendor read endpoints should expose profile and setup state asynchronously."""

    user = UnifiedUser.objects.create_user(
        email="vendor.async@fashionistar.test",
        password="Password123!",
        role=UnifiedUser.ROLE_VENDOR,
        is_active=True,
        is_verified=True,
    )
    profile = VendorProfile.objects.create(
        user=user,
        store_name="Atelier One",
        city="Umuahia",
        state="Abia",
        country="Nigeria",
    )
    VendorSetupState.objects.create(
        vendor=profile,
        profile_complete=True,
        bank_details=False,
        first_product=False,
        onboarding_done=False,
        current_step=2,
    )

    client = _auth_client(user)
    profile_response = client.get("/api/v1/ninja/vendor/profile/")
    setup_response = client.get("/api/v1/ninja/vendor/setup/")

    assert profile_response.status_code == 200
    assert profile_response.json()["user_email"] == "vendor.async@fashionistar.test"
    assert setup_response.status_code == 200
    assert setup_response.json()["current_step"] == 2


@pytest.mark.django_db
def test_vendor_ninja_profile_rejects_client_token():
    """Non-vendor roles should not pass the vendor async router guard."""

    user = UnifiedUser.objects.create_user(
        email="client.blocked@fashionistar.test",
        password="Password123!",
        role=UnifiedUser.ROLE_CLIENT,
        is_active=True,
        is_verified=True,
    )

    response = _auth_client(user).get("/api/v1/ninja/vendor/profile/")

    assert response.status_code == 403


@pytest.mark.django_db
def test_vendor_ninja_setup_allows_vendor_without_profile():
    """Vendor setup reads should return the default onboarding state pre-profile."""

    user = UnifiedUser.objects.create_user(
        email="vendor.no-profile@fashionistar.test",
        password="Password123!",
        role=UnifiedUser.ROLE_VENDOR,
        is_active=True,
        is_verified=True,
    )

    response = _auth_client(user).get("/api/v1/ninja/vendor/setup/")

    assert response.status_code == 200
    payload = response.json()
    assert payload["current_step"] == 1
    assert payload["profile_complete"] is False
    assert payload["completion_percentage"] == 0


@pytest.mark.django_db
def test_vendor_ninja_top_products_and_extended_dashboard():
    """Verify that top-products endpoint and extended dashboard return data for profile owners."""

    user = UnifiedUser.objects.create_user(
        email="vendor.dashboard@fashionistar.test",
        password="Password123!",
        role=UnifiedUser.ROLE_VENDOR,
        is_active=True,
        is_verified=True,
    )
    profile = VendorProfile.objects.create(
        user=user,
        store_name="Atelier Dashboard",
        city="Lagos",
        state="Lagos",
        country="Nigeria",
    )
    VendorSetupState.objects.create(
        vendor=profile,
        profile_complete=True,
        bank_details=True,
        first_product=True,
        onboarding_done=True,
        current_step=5,
    )

    client = _auth_client(user)

    # 1. Standalone top-products endpoint
    top_products_resp = client.get("/api/v1/ninja/vendor/top-products/")
    assert top_products_resp.status_code == 200
    assert isinstance(top_products_resp.json(), list)

    # 2. Extended dashboard payload containing top_products and revenue_trends
    dashboard_resp = client.get("/api/v1/ninja/vendor/dashboard/")
    assert dashboard_resp.status_code == 200
    dashboard_data = dashboard_resp.json()
    assert "top_products" in dashboard_data
    assert "revenue_trends" in dashboard_data
    assert isinstance(dashboard_data["top_products"], list)
    assert isinstance(dashboard_data["revenue_trends"], list)


@pytest.mark.django_db
def test_vendor_ninja_require_profile_endpoints_gate():
    """Verify that dashboard, profile, and top-products endpoints gate users without profile."""

    user = UnifiedUser.objects.create_user(
        email="vendor.noprof.gate@fashionistar.test",
        password="Password123!",
        role=UnifiedUser.ROLE_VENDOR,
        is_active=True,
        is_verified=True,
    )

    client = _auth_client(user)

    # These endpoints require a vendor profile and setup completion
    for path in ["/api/v1/ninja/vendor/dashboard/", "/api/v1/ninja/vendor/profile/", "/api/v1/ninja/vendor/top-products/"]:
        resp = client.get(path)
        assert resp.status_code == 403
        assert "setup is required" in resp.json().get("detail", "").lower()


@pytest.mark.django_db
def test_vendor_ninja_migrated_endpoints():
    """Verify that all migrated Django-Ninja async endpoints are fully operational."""

    user = UnifiedUser.objects.create_user(
        email="vendor.migrated@fashionistar.test",
        password="Password123!",
        role=UnifiedUser.ROLE_VENDOR,
        is_active=True,
        is_verified=True,
    )
    profile = VendorProfile.objects.create(
        user=user,
        store_name="Atelier Migrated",
        city="Calabar",
        state="Cross River",
        country="Nigeria",
    )
    VendorSetupState.objects.create(
        vendor=profile,
        profile_complete=True,
        bank_details=True,
        first_product=True,
        onboarding_done=True,
        current_step=5,
    )

    client = _auth_client(user)

    endpoints = [
        "/api/v1/ninja/vendor/analytics/",
        "/api/v1/ninja/vendor/analytics/revenue/",
        "/api/v1/ninja/vendor/analytics/orders/",
        "/api/v1/ninja/vendor/analytics/products/",
        "/api/v1/ninja/vendor/analytics/customers/",
        "/api/v1/ninja/vendor/analytics/categories/",
        "/api/v1/ninja/vendor/analytics/distribution/",
        "/api/v1/ninja/vendor/earnings/",
        "/api/v1/ninja/vendor/products/",
        "/api/v1/ninja/vendor/products/low-stock/",
        "/api/v1/ninja/vendor/products/top/",
        "/api/v1/ninja/vendor/orders/",
        "/api/v1/ninja/vendor/orders/status-counts/",
        "/api/v1/ninja/vendor/reviews/",
        "/api/v1/ninja/vendor/coupons/",
    ]

    for path in endpoints:
        resp = client.get(path)
        assert resp.status_code == 200, f"Endpoint {path} failed: {resp.content}"


