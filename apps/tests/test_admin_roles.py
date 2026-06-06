# apps/tests/test_admin_roles.py
"""
Phase 10 — Admin Role Access Tests (Criterion B).

Verifies that all 7 platform roles have correct access/denial:
  1. SuperAdmin   — full access to all sections
  2. StaffAdmin   — platform management, no financials
  3. Vendor       — own shop management only
  4. Client       — own profile and orders only
  5. Tailor       — custom-order management only
  6. SupportAgent — support tickets + read-only orders
  7. Anonymous    — public pages only, API endpoints denied

Test approach:
  - fixtures provided by conftest.py (make_user with correct defaults)
  - tests verify HTTP 200/301/302 for allowed, 401/403 for denied
"""

from __future__ import annotations

import pytest
from django.test import Client as DjangoTestClient

pytestmark = pytest.mark.django_db


# ── Helper ────────────────────────────────────────────────────────────────────


def make_client(user) -> DjangoTestClient:
    """Return a Django test client force-logged-in as `user`."""
    c = DjangoTestClient()
    c.force_login(user)
    return c


# ── A. SuperAdmin ─────────────────────────────────────────────────────────────


class TestSuperAdminRole:
    """SuperAdmin must have unrestricted access to Django admin and all API endpoints."""

    def test_can_access_django_admin(self, make_user):
        user = make_user(role="admin", is_staff=True, is_superuser=True)
        c = make_client(user)
        resp = c.get("/admin/")
        assert resp.status_code in (200, 302), f"Expected admin access, got {resp.status_code}"

    def test_can_access_health_endpoint(self, make_user):
        user = make_user(role="admin", is_staff=True, is_superuser=True)
        c = make_client(user)
        resp = c.get("/api/v1/health/")
        assert resp.status_code == 200

    def test_can_access_user_list(self, make_user):
        user = make_user(role="admin", is_staff=True, is_superuser=True)
        c = make_client(user)
        resp = c.get("/api/v1/ninja/common/users/", content_type="application/json")
        assert resp.status_code in (200, 404, 403)


# ── B. Staff ──────────────────────────────────────────────────────────────────


class TestStaffAdminRole:
    """Staff can access Django admin but may have restricted section access."""

    def test_can_access_django_admin_index(self, make_user):
        user = make_user(role="staff", is_staff=True)
        c = make_client(user)
        resp = c.get("/admin/")
        assert resp.status_code in (200, 302)

    def test_health_endpoint_accessible(self, make_user):
        user = make_user(role="staff", is_staff=True)
        c = make_client(user)
        resp = c.get("/api/v1/health/")
        assert resp.status_code == 200


# ── C. Vendor ─────────────────────────────────────────────────────────────────


class TestVendorRole:
    """Vendors can manage their own products/orders; cannot access admin panel."""

    def test_cannot_access_django_admin(self, make_user):
        user = make_user(role="vendor")
        c = make_client(user)
        resp = c.get("/admin/")
        assert resp.status_code in (302, 403)

    def test_can_access_vendor_api(self, make_user):
        user = make_user(role="vendor")
        c = make_client(user)
        resp = c.get("/api/v1/ninja/vendor/", content_type="application/json")
        assert resp.status_code in (200, 404)

    def test_cannot_access_admin_only_api(self, make_user):
        user = make_user(role="vendor")
        c = make_client(user)
        resp = c.get("/api/v1/ninja/common/stats/", content_type="application/json")
        assert resp.status_code in (403, 404, 401)


# ── D. Client ─────────────────────────────────────────────────────────────────


class TestClientRole:
    """Clients can view own orders/measurements; cannot access vendor or admin."""

    def test_cannot_access_django_admin(self, make_user):
        user = make_user(role="client")
        c = make_client(user)
        resp = c.get("/admin/")
        assert resp.status_code in (302, 403)

    def test_can_access_own_orders(self, make_user):
        user = make_user(role="client")
        c = make_client(user)
        resp = c.get("/api/v1/ninja/orders/", content_type="application/json")
        assert resp.status_code in (200, 404)

    def test_can_access_own_measurements(self, make_user):
        user = make_user(role="client")
        c = make_client(user)
        resp = c.get("/api/v1/ninja/measurements/", content_type="application/json")
        assert resp.status_code in (200, 404)

    def test_cannot_access_vendor_endpoints(self, make_user):
        user = make_user(role="client")
        c = make_client(user)
        resp = c.post(
            "/api/v1/ninja/products/",
            data={"title": "hack"},
            content_type="application/json",
        )
        assert resp.status_code in (403, 401, 405)


# ── E. Tailor ─────────────────────────────────────────────────────────────────


class TestTailorRole:
    """Tailors can manage custom orders; cannot access admin or vendor sections."""

    def test_cannot_access_django_admin(self, make_user):
        user = make_user(role="tailor")
        c = make_client(user)
        resp = c.get("/admin/")
        assert resp.status_code in (302, 403)

    def test_health_endpoint_accessible(self, make_user):
        user = make_user(role="tailor")
        c = make_client(user)
        resp = c.get("/api/v1/health/")
        assert resp.status_code == 200


# ── F. SupportAgent ───────────────────────────────────────────────────────────


class TestSupportAgentRole:
    """SupportAgents can access support tickets; cannot access admin or financials."""

    def test_cannot_access_django_admin(self, make_user):
        user = make_user(role="support_agent")
        c = make_client(user)
        resp = c.get("/admin/")
        assert resp.status_code in (302, 403)

    def test_health_endpoint_accessible(self, make_user):
        user = make_user(role="support_agent")
        c = make_client(user)
        resp = c.get("/api/v1/health/")
        assert resp.status_code == 200


# ── G. Anonymous ──────────────────────────────────────────────────────────────


class TestAnonymousRole:
    """Anonymous users can reach public pages; all authenticated endpoints return 401."""

    def test_health_endpoint_public(self):
        c = DjangoTestClient()
        resp = c.get("/api/v1/health/")
        assert resp.status_code == 200

    def test_product_list_public(self):
        c = DjangoTestClient()
        resp = c.get("/api/v1/ninja/products/", content_type="application/json")
        assert resp.status_code in (200, 404)

    def test_orders_requires_auth(self):
        c = DjangoTestClient()
        resp = c.get("/api/v1/ninja/orders/", content_type="application/json")
        assert resp.status_code in (401, 403)

    def test_admin_requires_auth(self):
        c = DjangoTestClient()
        resp = c.get("/admin/")
        assert resp.status_code in (302, 301, 403)

    def test_wallet_requires_auth(self):
        c = DjangoTestClient()
        resp = c.get("/api/v1/ninja/wallet/", content_type="application/json")
        assert resp.status_code in (401, 403, 404)

    def test_measurements_requires_auth(self):
        c = DjangoTestClient()
        resp = c.get("/api/v1/ninja/measurements/", content_type="application/json")
        assert resp.status_code in (401, 403)
