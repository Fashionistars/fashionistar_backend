# apps/admin_backend/permissions.py
"""
Admin-specific permission guards for the admin_backend API layer.

These are thin wrappers around the shared apps.common.permissions classes
that enforce admin/superuser-only access for all admin API endpoints.

DRF permissions: used in views.py (sync mutation views)
Ninja async permissions: used in api.py (async read endpoints)
"""

from __future__ import annotations

import logging

from django.contrib.auth.models import AnonymousUser
from ninja.security import HttpBearer
from rest_framework.permissions import BasePermission

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# DRF Sync Permission (for mutation views)
# ─────────────────────────────────────────────────────────────────────────────

class IsAdminUser(BasePermission):
    """
    DRF permission: allows only admin-role users and Django superusers.
    Used on all DRF sync mutation views in each app's admin_backend/views.py.
    """

    message = "Admin or superuser access required."

    def has_permission(self, request, view) -> bool:
        user = getattr(request, "user", None)
        if not user or isinstance(user, AnonymousUser):
            return False
        if not getattr(user, "is_authenticated", False):
            return False
        if getattr(user, "is_superuser", False):
            return True
        role = getattr(user, "role", "")
        return role in ("admin", "super_admin")


class IsSuperuserOnly(BasePermission):
    """
    DRF permission: restricts to Django superusers only.
    Used for destructive financial operations (wallet freeze, manual credit, payout).
    """

    message = "Superuser access required for this operation."

    def has_permission(self, request, view) -> bool:
        user = getattr(request, "user", None)
        if not user or isinstance(user, AnonymousUser):
            return False
        return bool(
            getattr(user, "is_authenticated", False)
            and getattr(user, "is_superuser", False)
        )


# ─────────────────────────────────────────────────────────────────────────────
# Django Ninja Bearer Auth (for async read endpoints)
# ─────────────────────────────────────────────────────────────────────────────

class AdminJWTBearer(HttpBearer):
    """
    Ninja async bearer token auth that validates JWT and enforces admin role.

    The token is the standard simplejwt access token. This bearer class:
    1. Decodes the JWT via simplejwt
    2. Loads the user from DB
    3. Checks admin/superuser role
    4. Attaches user to request

    Used on all Ninja async read routers in each app's admin_backend/api.py.
    """

    async def authenticate(self, request, token: str):
        try:
            from rest_framework_simplejwt.tokens import UntypedToken
            from rest_framework_simplejwt.exceptions import TokenError
            from django.contrib.auth import get_user_model

            User = get_user_model()

            # Validate token
            UntypedToken(token)

            # Decode payload
            import asyncio
            from rest_framework_simplejwt.tokens import AccessToken
            access = AccessToken(token)
            user_id = access["user_id"]

            # Async user fetch
            user = await User.objects.select_related().aget(pk=user_id)

            # Role check
            if not (
                getattr(user, "is_superuser", False)
                or getattr(user, "role", "") in ("admin", "super_admin")
            ):
                logger.warning(
                    "AdminJWTBearer: user %s (role=%s) denied admin access",
                    user.pk,
                    getattr(user, "role", "?"),
                )
                return None

            return user

        except Exception as exc:
            logger.debug("AdminJWTBearer auth failure: %s", exc)
            return None


# Singleton for use in api.py routers
admin_auth = AdminJWTBearer()
