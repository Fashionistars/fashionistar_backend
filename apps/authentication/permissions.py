"""Authentication-domain compatibility permissions."""

from __future__ import annotations

import logging

from rest_framework import permissions

from apps.common.roles import is_client_role, is_vendor_role

logger = logging.getLogger("application")


class IsTokenValid(permissions.BasePermission):
    """Allow any authenticated user with a valid token."""

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated)


class IsVendorUser(permissions.BasePermission):
    """Allow access only to vendor-role accounts."""

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and is_vendor_role(getattr(request.user, "role", None))
            and request.user.vendor_profile is not None
        )


class IsClientUser(permissions.BasePermission):
    """Allow access only to client-role accounts."""

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and is_client_role(getattr(request.user, "role", None))
            and request.user.client_profile is not None

        )
