"""Focused tests for client async Ninja read endpoints."""

from __future__ import annotations

import pytest
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.authentication.models import UnifiedUser
from apps.client.models import ClientAddress, ClientProfile


def _auth_client(user: UnifiedUser) -> APIClient:
    """Return an API client authenticated with a SimpleJWT access token."""

    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(user).access_token}")
    return client


@pytest.mark.django_db
def test_client_ninja_profile_returns_profile_and_addresses():
    """Client profile read should expose the expected async payload."""

    user = UnifiedUser.objects.create_user(
        email="client.async@fashionistar.test",
        password="Password123!",
        role=UnifiedUser.ROLE_CLIENT,
        is_active=True,
        is_verified=True,
    )
    profile = ClientProfile.objects.create(
        user=user,
        bio="Ready to shop",
        default_shipping_address="12 Okigwe Street",
        state="Lagos",
        country="Nigeria",
        preferred_size="M",
        style_preferences=["casual"],
        favourite_colours=["black"],
    )
    ClientAddress.objects.create(
        client=profile,
        label="Home",
        full_name="Client Example",
        phone="+2348012345678",
        street_address="12 Okigwe Street",
        city="Ikeja",
        state="Lagos",
        country="Nigeria",
        postal_code="100271",
        is_default=True,
    )

    response = _auth_client(user).get("/api/v1/ninja/client/profile/")

    assert response.status_code == 200
    payload = response.json()
    assert payload["user_email"] == "client.async@fashionistar.test"
    assert payload["default_shipping_address"] == "12 Okigwe Street"
    assert len(payload["addresses"]) == 1


@pytest.mark.django_db
def test_client_ninja_profile_rejects_vendor_token():
    """Non-client roles should not pass the client async router guard."""

    user = UnifiedUser.objects.create_user(
        email="vendor.blocked@fashionistar.test",
        password="Password123!",
        role=UnifiedUser.ROLE_VENDOR,
        is_active=True,
        is_verified=True,
    )

    response = _auth_client(user).get("/api/v1/ninja/client/profile/")

    assert response.status_code == 403
