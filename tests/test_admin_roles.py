"""
FASHIONISTAR — Phase 10 Test Suite: Admin Role Access Tests

Tests all 7+ roles against every admin section to verify RBAC correctness.
Uses pytest parametrize for exhaustive combinatorial coverage.

Run:
    pytest tests/test_admin_roles.py -v --tb=short
"""

from __future__ import annotations

import pytest
from django.test import RequestFactory
from django.contrib.admin.sites import AdminSite
from rest_framework.test import APIClient
from rest_framework import status


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def make_user(db):
    """Factory fixture: create a user with a specific role."""
    from apps.authentication.models import UnifiedUser

    def _make(role: str, email: str | None = None) -> UnifiedUser:
        _email = email or f"{role.lower().replace('_', '')}@fashionistar.test"
        user = UnifiedUser.objects.create_user(
            email=_email,
            password="TestPass@2026!",
            role=role.lower(),
            is_active=True,
            is_verified=True,
        )
        return user

    return _make


@pytest.fixture
def get_token(api_client, make_user):
    """Get JWT token for a role."""
    def _get(role: str) -> str:
        user = make_user(role)
        resp = api_client.post(
            "/api/v1/auth/login/",
            {"email": user.email, "password": "TestPass@2026!"},
            format="json",
        )
        return resp.data.get("data", {}).get("access", "")
    return _get


# ── Parametrized Role × Endpoint Matrix ──────────────────────────────────────


ALL_ROLES = [
    "CLIENT", "VENDOR", "STAFF", "ADMIN",
    "EDITOR", "SUPPORT", "MODERATOR", "SUPER_ADMIN",
]

ADMIN_ONLY_ENDPOINTS = [
    "/api/v1/admin_backend/auth/users/",
    "/api/v1/admin_backend/audit/",
    "/api/v1/admin_backend/settings/",
    "/api/v1/admin_backend/kyc/",
    "/api/v1/admin_backend/payment/",
]

VENDOR_ENDPOINTS = [
    "/api/v1/ninja/vendor/dashboard/",
    "/api/v1/ninja/vendor/profile/",
    "/api/v1/ninja/vendor/earnings/",
    "/api/v1/ninja/vendor/products/",
    "/api/v1/ninja/vendor/orders/",
]

CLIENT_ENDPOINTS = [
    "/api/v1/client/profile/",
    "/api/v1/measurements/",
    "/api/v1/cart/current/",
    "/api/v1/orders/",
]

PUBLIC_ENDPOINTS = [
    "/api/v1/health/",
    "/api/v1/ninja/products/",
    "/api/v1/ninja/categories/",
]


@pytest.mark.django_db
class TestPublicEndpoints:
    """Unauthenticated access to public endpoints — must always return 200."""

    @pytest.mark.parametrize("endpoint", PUBLIC_ENDPOINTS)
    def test_public_endpoint_unauthenticated(self, api_client, endpoint):
        resp = api_client.get(endpoint)
        assert resp.status_code in (200, 301, 302), (
            f"Public endpoint {endpoint} returned {resp.status_code}"
        )


class TestAdminOnlyEndpoints:
    """Only ADMIN / SUPER_ADMIN may access admin endpoints."""

    @pytest.mark.django_db
    @pytest.mark.parametrize("endpoint", ADMIN_ONLY_ENDPOINTS)
    @pytest.mark.parametrize("role", ALL_ROLES)
    def test_admin_endpoint_role_access(self, api_client, make_user, endpoint, role):
        user = make_user(role)
        api_client.force_authenticate(user=user)
        resp = api_client.get(endpoint)

        if role in ("ADMIN", "SUPER_ADMIN"):
            # Admin roles must be able to access
            assert resp.status_code in (200, 404), (
                f"ADMIN cannot access {endpoint}: got {resp.status_code}"
            )
        else:
            # Non-admin roles must be rejected
            assert resp.status_code in (403, 404), (
                f"Non-admin role {role} accessed admin endpoint {endpoint}: got {resp.status_code}"
            )


class TestVendorEndpoints:
    """VENDOR and SUPER_VENDOR may access vendor endpoints."""

    @pytest.mark.django_db
    @pytest.mark.parametrize("endpoint", VENDOR_ENDPOINTS)
    @pytest.mark.parametrize("role", ALL_ROLES)
    def test_vendor_endpoint_role_access(self, api_client, make_user, endpoint, role):
        user = make_user(role)
        api_client.force_authenticate(user=user)
        resp = api_client.get(endpoint)

        if role in ("VENDOR", "SUPER_VENDOR", "ADMIN", "SUPER_ADMIN"):
            assert resp.status_code in (200, 404), (
                f"Vendor role {role} cannot access {endpoint}: got {resp.status_code}"
            )
        else:
            assert resp.status_code in (403, 404), (
                f"Non-vendor role {role} accessed vendor endpoint {endpoint}: got {resp.status_code}"
            )


class TestClientEndpoints:
    """CLIENT and SUPER_CLIENT may access client-facing endpoints."""

    @pytest.mark.django_db
    @pytest.mark.parametrize("endpoint", CLIENT_ENDPOINTS)
    @pytest.mark.parametrize("role", ["CLIENT", "VENDOR", "ADMIN"])
    def test_client_endpoint_access(self, api_client, make_user, endpoint, role):
        user = make_user(role)
        api_client.force_authenticate(user=user)
        resp = api_client.get(endpoint)
        # All authenticated roles can access client endpoints (own data)
        assert resp.status_code in (200, 404), (
            f"Role {role} cannot access {endpoint}: got {resp.status_code}"
        )


@pytest.mark.django_db
class TestUnauthenticatedProtectedEndpoints:
    """All protected endpoints must reject unauthenticated requests."""

    PROTECTED = ADMIN_ONLY_ENDPOINTS + VENDOR_ENDPOINTS + CLIENT_ENDPOINTS

    @pytest.mark.parametrize("endpoint", PROTECTED)
    def test_unauthenticated_rejected(self, api_client, endpoint):
        resp = api_client.get(endpoint)
        assert resp.status_code in (401, 403), (
            f"Endpoint {endpoint} did not reject unauthenticated access: {resp.status_code}"
        )


class TestObjectLevelPermissions:
    """BOLA (OWASP API1) — users cannot access other users' resources."""

    @pytest.mark.django_db
    def test_client_cannot_read_other_client_measurements(self, api_client, make_user):
        from apps.measurements.models import MeasurementProfile

        owner = make_user("CLIENT", "owner@test.com")
        attacker = make_user("CLIENT", "attacker@test.com")

        # Create a measurement profile for owner
        profile = MeasurementProfile.objects.create(
            owner=owner, name="My Profile",
            height=175.0, weight_kg=70.0,
        )

        api_client.force_authenticate(user=attacker)
        resp = api_client.get(f"/api/v1/measurements/{profile.id}/")
        assert resp.status_code in (403, 404), (
            f"BOLA: attacker accessed owner's measurement profile: {resp.status_code}"
        )

    @pytest.mark.django_db
    def test_vendor_cannot_read_other_vendor_orders(self, api_client, make_user):
        from apps.order.models import Order
        from apps.vendor.models import VendorProfile

        vendor_a = make_user("VENDOR", "vendora@test.com")
        vendor_b = make_user("VENDOR", "vendorb@test.com")

        api_client.force_authenticate(user=vendor_b)
        # Try to list orders for vendor_a's store
        resp = api_client.get(f"/api/v1/vendor/orders/?vendor_id={vendor_a.id}")
        # Must not return vendor_a's orders
        assert resp.status_code in (200, 403, 404)
        if resp.status_code == 200:
            data = resp.json().get("data", {})
            results = data.get("results", [])
            for order in results:
                assert order.get("vendor") != str(vendor_a.id), (
                    "BOLA: vendor_b can see vendor_a's orders"
                )
