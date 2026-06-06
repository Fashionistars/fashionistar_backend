# apps/tests/conftest.py
"""
Shared pytest fixtures for the FASHIONISTAR test suite.

Provides:
  - make_user: Factory fixture that creates UnifiedUser instances with all
    required defaults set correctly (bypasses manager quirks).
  - api_client: Authenticated DRF APIClient for a given user.
  - admin_client / vendor_client / client_user_client: Role-specific clients.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

User = get_user_model()

# ── Default field overrides required by UnifiedUser model ────────────────────
# These ensure ValidationError is not raised for JSONFields with default=list
# that nevertheless fail blank validation in the manager.

_USER_DEFAULTS: dict[str, Any] = {
    "is_active": True,
    "is_verified": True,
    "objected_processing_purposes": [],  # GDPR Art.21 JSONField — must not be blank
}


# ── Core factory ─────────────────────────────────────────────────────────────

@pytest.fixture
def make_user(db):
    """
    Factory fixture: ``make_user(role='client', **kwargs) -> UnifiedUser``.

    Usage::

        def test_something(make_user):
            user = make_user(role="vendor")
            user = make_user(role="admin", is_staff=True, is_superuser=True)
    """
    def _factory(role: str = "client", **kwargs) -> Any:
        uid = uuid.uuid4().hex[:8]
        fields = {**_USER_DEFAULTS, "role": role, **kwargs}
        email = kwargs.get("email", f"test_{role}_{uid}@fashionistar.ng")
        password = kwargs.pop("password", "TestPass!2026")
        user = User.objects.create_user(
            email=email,
            password=password,
            **{k: v for k, v in fields.items() if k != "email"},
        )
        return user

    return _factory


# ── Wallet factory ────────────────────────────────────────────────────────────

@pytest.fixture
def make_wallet(db):
    """
    Factory: ``make_wallet(user, balance=50000) -> Wallet``.
    Creates a Wallet for the given user with an initial balance.
    """
    from apps.wallet.models import Wallet

    def _factory(user, balance: Decimal = Decimal("50000.00")) -> Any:
        return Wallet.objects.create(
            user=user,
            available_balance=balance,
            held_balance=Decimal("0.00"),
            total_credited=balance,
            total_debited=Decimal("0.00"),
            currency="NGN",
        )

    return _factory


# ── API client helpers ────────────────────────────────────────────────────────

@pytest.fixture
def api_client():
    """Unauthenticated DRF API client."""
    return APIClient()


@pytest.fixture
def auth_client(make_user, api_client):
    """
    Authenticated client factory.

    Usage::

        def test_something(auth_client, make_user):
            vendor = make_user(role="vendor")
            client = auth_client(vendor)
            response = client.get("/api/v1/vendor/products/")
    """
    def _factory(user):
        client = APIClient()
        client.force_authenticate(user=user)
        return client

    return _factory


# ── Role-specific convenience fixtures ───────────────────────────────────────

@pytest.fixture
def superadmin_user(make_user):
    return make_user(role="admin", is_staff=True, is_superuser=True)


@pytest.fixture
def vendor_user(make_user):
    return make_user(role="vendor")


@pytest.fixture
def client_user(make_user):
    return make_user(role="client")


@pytest.fixture
def staff_user(make_user):
    return make_user(role="staff", is_staff=True)


@pytest.fixture
def vendor_with_wallet(make_user, make_wallet):
    """Vendor user with a ₦50,000 wallet — ready for payout tests."""
    user = make_user(role="vendor")
    wallet = make_wallet(user, balance=Decimal("50000.00"))
    return user, wallet
