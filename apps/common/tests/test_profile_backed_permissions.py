"""Regression tests for shared role and profile-backed permissions."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from apps.authentication.models import UnifiedUser
from apps.authentication.permissions import IsClientUser, IsVendorUser
from apps.client.models import ClientProfile
from apps.common.permissions import (
    IsClient,
    IsClientWithProfile,
    IsVendor,
    IsVendorWithProfile,
)
from apps.vendor.models import VendorProfile


def _request_for(user):
    """Return a minimal request-like object for DRF permission checks."""

    return SimpleNamespace(user=user)


@pytest.mark.django_db
def test_vendor_role_permission_allows_setup_before_profile():
    """Vendor setup must remain reachable before VendorProfile provisioning."""

    user = UnifiedUser.objects.create_user(
        email="vendor.setup@fashionistar.test",
        password="Password123!",
        role=UnifiedUser.ROLE_VENDOR,
        is_active=True,
        is_verified=True,
    )

    request = _request_for(user)

    assert IsVendor().has_permission(request, None) is True
    assert IsVendorWithProfile().has_permission(request, None) is False
    assert IsVendorUser().has_permission(request, None) is False


@pytest.mark.django_db
def test_vendor_profile_permission_uses_reverse_one_to_one_relation():
    """Protected vendor APIs should pass once request.user.vendor_profile exists."""

    user = UnifiedUser.objects.create_user(
        email="vendor.profile@fashionistar.test",
        password="Password123!",
        role=UnifiedUser.ROLE_VENDOR,
        is_active=True,
        is_verified=True,
    )
    VendorProfile.objects.create(user=user, store_name="Profiled Atelier")

    request = _request_for(user)

    assert IsVendorWithProfile().has_permission(request, None) is True
    assert IsVendorUser().has_permission(request, None) is True


@pytest.mark.django_db
def test_client_profile_permission_uses_reverse_one_to_one_relation():
    """Protected client APIs can require request.user.client_profile safely."""

    user = UnifiedUser.objects.create_user(
        email="client.profile@fashionistar.test",
        password="Password123!",
        role=UnifiedUser.ROLE_CLIENT,
        is_active=True,
        is_verified=True,
    )

    request = _request_for(user)

    assert IsClient().has_permission(request, None) is True
    assert IsClientWithProfile().has_permission(request, None) is False
    assert IsClientUser().has_permission(request, None) is False

    ClientProfile.objects.create(user=user)
    user.refresh_from_db()
    request = _request_for(user)

    assert IsClientWithProfile().has_permission(request, None) is True
    assert IsClientUser().has_permission(request, None) is True
