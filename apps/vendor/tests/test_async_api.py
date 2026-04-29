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
