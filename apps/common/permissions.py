"""
Shared permission classes for the Fashionistar platform.

This module centralizes the most common RBAC checks used across the modular
backend. The rules intentionally mirror ``UnifiedUser.ROLE_CHOICES`` so
permission behavior stays aligned with the authentication domain.
"""

from __future__ import annotations

import logging

from django.core.exceptions import ObjectDoesNotExist
from django.contrib.auth.models import AnonymousUser
from rest_framework.permissions import BasePermission

from apps.common.roles import (
    CLIENT_ROLES,
    EDITOR_ROLES,
    MODERATOR_ROLES,
    SALES_ROLES,
    STAFF_ROLES,
    SUPPORT_ROLES,
    VENDOR_ROLES,
    has_any_role,
    is_admin_role,
    is_staff_role,
    normalize_role,
)

permission_logger = logging.getLogger("permissions")


def _get_user(request):
    """Return the best-effort user object from the request."""

    return getattr(request, "user", None)


def _is_authenticated_user(user) -> bool:
    """Return True when the object is an authenticated Django user."""

    return bool(
        user
        and not isinstance(user, AnonymousUser)
        and getattr(user, "is_authenticated", False)
    )


def _get_role(user) -> str:
    """Return the normalized role for a user-like object."""

    return normalize_role(getattr(user, "role", ""))


def _has_any_role(user, *roles: str) -> bool:
    """Check whether a user has any role from the provided set."""

    return has_any_role(_get_role(user), roles)


def _get_reverse_relation_or_none(user, related_name: str):
    """Return a reverse one-to-one relation when it exists, otherwise None."""

    try:
        return getattr(user, related_name)
    except (AttributeError, ObjectDoesNotExist):
        return None
    except Exception as exc:  # noqa: BLE001
        permission_logger.error(
            "Error resolving reverse relation '%s' for %s: %s",
            related_name,
            getattr(user, "pk", "?"),
            exc,
        )
        return None


def _log_permission_result(user, *, label: str, granted: bool, async_mode: bool) -> None:
    """Emit a concise audit log for a role permission decision."""

    identifier = getattr(user, "email", None) or getattr(user, "pk", "anonymous")
    suffix = " (async)" if async_mode else ""
    if granted:
        permission_logger.info("%s access granted%s for %s", label, suffix, identifier)
    else:
        permission_logger.warning("%s access denied%s for %s", label, suffix, identifier)


class _RolePermission(BasePermission):
    """Base class for simple role-driven permission checks."""

    allowed_roles: tuple[str, ...] = ()
    role_label: str = "Role"

    def _user_has_permission(self, user) -> bool:
        return _has_any_role(user, *self.allowed_roles)

    def has_permission(self, request, view) -> bool:
        try:
            user = _get_user(request)
            if not _is_authenticated_user(user):
                permission_logger.warning(
                    "%s access denied for anonymous/unauthenticated request.",
                    self.role_label,
                )
                return False

            granted = self._user_has_permission(user)
            _log_permission_result(
                user,
                label=self.role_label,
                granted=granted,
                async_mode=False,
            )
            return granted
        except Exception as exc:  # noqa: BLE001
            permission_logger.error(
                "Error evaluating %s permission for %s: %s",
                self.role_label,
                getattr(request, "user", None),
                exc,
            )
            return False

    async def has_permission_async(self, request, view) -> bool:
        try:
            user = await request.auser() if hasattr(request, "auser") else _get_user(request)
            if not _is_authenticated_user(user):
                permission_logger.warning(
                    "%s access denied (async) for anonymous/unauthenticated request.",
                    self.role_label,
                )
                return False

            granted = self._user_has_permission(user)
            _log_permission_result(
                user,
                label=self.role_label,
                granted=granted,
                async_mode=True,
            )
            return granted
        except Exception as exc:  # noqa: BLE001
            permission_logger.error(
                "Error evaluating %s permission (async) for %s: %s",
                self.role_label,
                getattr(request, "user", None),
                exc,
            )
            return False


class IsVendor(_RolePermission):
    """Allow access to vendor and super-vendor accounts."""

    allowed_roles = tuple(VENDOR_ROLES)
    role_label = "Vendor"
    message = "You must be a vendor to access this resource."


class IsClient(_RolePermission):
    """Allow access to client and super-client accounts."""

    allowed_roles = tuple(CLIENT_ROLES)
    role_label = "Client"
    message = "You must be a client to access this resource."


class IsVendorWithProfile(_RolePermission):
    """
    Allow vendor-role users only after their VendorProfile exists.

    Use ``IsVendor`` for onboarding/setup routes where the profile may not
    exist yet. Use this permission for protected vendor workspaces and APIs
    that dereference ``request.user.vendor_profile``.
    """

    allowed_roles = tuple(VENDOR_ROLES)
    role_label = "VendorProfile"
    message = "Vendor setup is required before accessing this resource."

    def _user_has_permission(self, user) -> bool:
        return bool(
            _has_any_role(user, *self.allowed_roles)
            and _get_reverse_relation_or_none(user, "vendor_profile") is not None
        )


class IsClientWithProfile(_RolePermission):
    """
    Allow client-role users only after their ClientProfile exists.

    Client profile auto-provisioning should keep using ``IsClient``. Protected
    client APIs that require ``request.user.client_profile`` should use this
    stricter guard.
    """

    allowed_roles = tuple(CLIENT_ROLES)
    role_label = "ClientProfile"
    message = "Client profile setup is required before accessing this resource."

    def _user_has_permission(self, user) -> bool:
        return bool(
            _has_any_role(user, *self.allowed_roles)
            and _get_reverse_relation_or_none(user, "client_profile") is not None
        )


IsProvisionedVendor = IsVendorWithProfile
IsProvisionedClient = IsClientWithProfile


class IsSupport(_RolePermission):
    """Allow access to support and super-support accounts."""

    allowed_roles = tuple(SUPPORT_ROLES)
    role_label = "Support"
    message = "You must be support staff to access this resource."


class IsEditor(_RolePermission):
    """Allow access to editor-role users and compatibility reviewer aliases."""

    allowed_roles = tuple(EDITOR_ROLES)
    role_label = "Editor"
    message = "You must be an editor to access this resource."


class IsSales(_RolePermission):
    """Allow access to assistant/sales-role users."""

    allowed_roles = tuple(SALES_ROLES)
    role_label = "Sales"
    message = "You must be sales staff to access this resource."


class IsModerator(_RolePermission):
    """Allow access to moderation users."""

    allowed_roles = tuple(MODERATOR_ROLES)
    role_label = "Moderator"
    message = "You must be a moderator to access this resource."


class IsStaff(BasePermission):
    """Allow access to all internal staff and privileged admin roles."""

    message = "You must be staff to access this resource."

    staff_roles: tuple[str, ...] = tuple(STAFF_ROLES)

    def _user_has_permission(self, user) -> bool:
        return bool(
            getattr(user, "is_staff", False)
            or getattr(user, "is_superuser", False)
            or is_staff_role(_get_role(user))
        )

    def has_permission(self, request, view) -> bool:
        try:
            user = _get_user(request)
            if not _is_authenticated_user(user):
                permission_logger.warning(
                    "Staff access denied for anonymous/unauthenticated request."
                )
                return False

            granted = self._user_has_permission(user)
            _log_permission_result(user, label="Staff", granted=granted, async_mode=False)
            return granted
        except Exception as exc:  # noqa: BLE001
            permission_logger.error(
                "Error checking staff permission for %s: %s",
                getattr(request, "user", None),
                exc,
            )
            return False

    async def has_permission_async(self, request, view) -> bool:
        try:
            user = await request.auser() if hasattr(request, "auser") else _get_user(request)
            if not _is_authenticated_user(user):
                permission_logger.warning(
                    "Staff access denied (async) for anonymous/unauthenticated request."
                )
                return False

            granted = self._user_has_permission(user)
            _log_permission_result(user, label="Staff", granted=granted, async_mode=True)
            return granted
        except Exception as exc:  # noqa: BLE001
            permission_logger.error(
                "Error checking staff permission (async) for %s: %s",
                getattr(request, "user", None),
                exc,
            )
            return False


class IsAdminOrSuperuser(BasePermission):
    """Allow access to admin-grade accounts and Django superusers."""

    message = "You must be an admin to access this resource."

    def _user_has_permission(self, user) -> bool:
        return bool(
            getattr(user, "is_superuser", False)
            or is_admin_role(_get_role(user))
        )

    def has_permission(self, request, view) -> bool:
        try:
            user = _get_user(request)
            if not _is_authenticated_user(user):
                permission_logger.warning(
                    "Admin access denied for anonymous/unauthenticated request."
                )
                return False

            granted = self._user_has_permission(user)
            _log_permission_result(user, label="Admin", granted=granted, async_mode=False)
            return granted
        except Exception as exc:  # noqa: BLE001
            permission_logger.error(
                "Error checking admin permission for %s: %s",
                getattr(request, "user", None),
                exc,
            )
            return False

    async def has_permission_async(self, request, view) -> bool:
        try:
            user = await request.auser() if hasattr(request, "auser") else _get_user(request)
            if not _is_authenticated_user(user):
                permission_logger.warning(
                    "Admin access denied (async) for anonymous/unauthenticated request."
                )
                return False

            granted = self._user_has_permission(user)
            _log_permission_result(user, label="Admin", granted=granted, async_mode=True)
            return granted
        except Exception as exc:  # noqa: BLE001
            permission_logger.error(
                "Error checking admin permission (async) for %s: %s",
                getattr(request, "user", None),
                exc,
            )
            return False


class IsOwner(BasePermission):
    """Object-level permission that restricts access to the owning user."""

    message = "You must be the owner of this resource to access it."

    def has_object_permission(self, request, view, obj) -> bool:
        try:
            user = _get_user(request)
            if not _is_authenticated_user(user):
                permission_logger.warning("Owner access denied for anonymous request.")
                return False

            granted = getattr(obj, "user", None) == user
            _log_permission_result(user, label="Owner", granted=granted, async_mode=False)
            return granted
        except Exception as exc:  # noqa: BLE001
            permission_logger.error(
                "Error checking owner permission for %s on %s: %s",
                getattr(request, "user", None),
                obj,
                exc,
            )
            return False

    async def has_object_permission_async(self, request, view, obj) -> bool:
        try:
            user = await request.auser() if hasattr(request, "auser") else _get_user(request)
            if not _is_authenticated_user(user):
                permission_logger.warning(
                    "Owner access denied (async) for anonymous request."
                )
                return False

            granted = getattr(obj, "user", None) == user
            _log_permission_result(user, label="Owner", granted=granted, async_mode=True)
            return granted
        except Exception as exc:  # noqa: BLE001
            permission_logger.error(
                "Error checking owner permission (async) for %s on %s: %s",
                getattr(request, "user", None),
                obj,
                exc,
            )
            return False


class IsAuthenticatedAndActive(BasePermission):
    """
    Ensure the request is authenticated and the account is active.

    This is stricter than DRF's built-in authentication check because it also
    blocks suspended accounts carrying otherwise valid JWTs.
    """

    message = "Your account is inactive. Please contact support."

    def has_permission(self, request, view) -> bool:
        try:
            user = _get_user(request)
            if not _is_authenticated_user(user):
                permission_logger.warning(
                    "IsAuthenticatedAndActive blocked anonymous/unauthenticated request."
                )
                return False

            if not getattr(user, "is_active", False):
                permission_logger.warning(
                    "IsAuthenticatedAndActive blocked inactive account '%s'.",
                    getattr(user, "email", getattr(user, "pk", "?")),
                )
                return False

            return True
        except Exception as exc:  # noqa: BLE001
            permission_logger.error(
                "IsAuthenticatedAndActive error for '%s': %s",
                getattr(request, "user", None),
                exc,
            )
            return False

    async def has_permission_async(self, request, view) -> bool:
        try:
            user = await request.auser() if hasattr(request, "auser") else _get_user(request)
            if not _is_authenticated_user(user):
                return False
            if not getattr(user, "is_active", False):
                permission_logger.warning(
                    "IsAuthenticatedAndActive blocked inactive account (async) '%s'.",
                    getattr(user, "email", getattr(user, "pk", "?")),
                )
                return False
            return True
        except Exception as exc:  # noqa: BLE001
            permission_logger.error("IsAuthenticatedAndActive async error: %s", exc)
            return False


class IsVerifiedUser(BasePermission):
    """Require authentication, an active account, and successful verification."""

    message = (
        "Your account is not yet verified. "
        "Please complete OTP verification to access this resource."
    )

    def has_permission(self, request, view) -> bool:
        try:
            user = _get_user(request)
            if not _is_authenticated_user(user):
                permission_logger.warning("IsVerifiedUser blocked unauthenticated request.")
                return False
            if not getattr(user, "is_active", False):
                permission_logger.warning(
                    "IsVerifiedUser blocked inactive account '%s'.",
                    getattr(user, "email", getattr(user, "pk", "?")),
                )
                return False
            if not getattr(user, "is_verified", False):
                permission_logger.warning(
                    "IsVerifiedUser blocked unverified account '%s'.",
                    getattr(user, "email", getattr(user, "pk", "?")),
                )
                return False
            return True
        except Exception as exc:  # noqa: BLE001
            permission_logger.error(
                "IsVerifiedUser error for '%s': %s",
                getattr(request, "user", None),
                exc,
            )
            return False

    async def has_permission_async(self, request, view) -> bool:
        try:
            user = await request.auser() if hasattr(request, "auser") else _get_user(request)
            if not _is_authenticated_user(user):
                return False
            if not getattr(user, "is_active", False):
                return False
            if not getattr(user, "is_verified", False):
                permission_logger.warning(
                    "IsVerifiedUser blocked unverified account (async) '%s'.",
                    getattr(user, "email", getattr(user, "pk", "?")),
                )
                return False
            return True
        except Exception as exc:  # noqa: BLE001
            permission_logger.error("IsVerifiedUser async error: %s", exc)
            return False


class RateLimitPermission(BasePermission):
    """
    Simple cache-backed sliding-window rate limiter.

    The implementation deliberately fails open when the cache backend is
    unavailable so temporary infrastructure issues do not block legitimate
    platform traffic.
    """

    max_requests: int = 100
    window_seconds: int = 3600
    message = "Too many requests. Please slow down and try again later."

    @staticmethod
    def _get_client_ip(request) -> str:
        """Extract the real client IP, respecting proxy headers."""

        x_forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
        if x_forwarded:
            return x_forwarded.split(",")[0].strip()
        return request.META.get("REMOTE_ADDR", "0.0.0.0")

    def _get_cache_key(self, request) -> str:
        user = getattr(request, "user", None)
        if user and getattr(user, "is_authenticated", False):
            identity = f"user:{user.pk}"
        else:
            identity = f"ip:{self._get_client_ip(request)}"
        return f"ratelimit:{identity}"

    def has_permission(self, request, view) -> bool:
        try:
            from django.core.cache import cache

            cache_key = self._get_cache_key(request)
            current = cache.get(cache_key, 0) + 1
            cache.set(cache_key, current, timeout=self.window_seconds)

            if current > self.max_requests:
                permission_logger.warning(
                    "RateLimitPermission hit limit for key='%s' (%d/%d).",
                    cache_key,
                    current,
                    self.max_requests,
                )
                return False
            return True
        except Exception as exc:  # noqa: BLE001
            permission_logger.error("RateLimitPermission error (fail-open): %s", exc)
            return True

    async def has_permission_async(self, request, view) -> bool:
        import asyncio

        try:
            return await asyncio.to_thread(self.has_permission, request, view)
        except Exception as exc:  # noqa: BLE001
            permission_logger.error(
                "RateLimitPermission async error (fail-open): %s",
                exc,
            )
            return True


def require_verification(func):
    """Apply ``IsVerifiedUser`` to an individual DRF view method."""

    from functools import wraps

    from rest_framework import status

    from apps.common.renderers import error_response

    @wraps(func)
    def wrapper(self, request, *args, **kwargs):
        permission = IsVerifiedUser()
        if not permission.has_permission(request, self):
            return error_response(
                message=permission.message,
                status=status.HTTP_403_FORBIDDEN,
                code="account_not_verified",
            )
        return func(self, request, *args, **kwargs)

    return wrapper
