"""Authentication-domain compatibility permissions."""

from __future__ import annotations

import logging

from rest_framework import permissions

from apps.common.permissions import IsClientWithProfile, IsVendorWithProfile

logger = logging.getLogger("application")


class IsTokenValid(permissions.BasePermission):
    """Allow any authenticated user with a valid token."""

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated)


class IsVendorUser(IsVendorWithProfile):
    """Compatibility alias for vendor APIs that require an existing profile."""


class IsClientUser(IsClientWithProfile):
    """Compatibility alias for client APIs that require an existing profile."""
