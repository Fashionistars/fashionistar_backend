# apps/product/permissions.py
"""
Shared permission classes for the Fashionistar platform.

This module centralizes the most common RBAC checks used across the modular
backend. The rules intentionally mirror ``UnifiedUser.ROLE_CHOICES`` so
permission behavior stays aligned with the authentication domain.
"""

from __future__ import annotations


import logging

from django.core.exceptions import ObjectDoesNotExist, PermissionDenied
from rest_framework import permissions
from django.contrib.auth.models import AnonymousUser
from rest_framework.permissions import BasePermission


from apps.product.models import Product


from apps.common.permissions import IsVerifiedUser
from apps.common.roles import (
    VENDOR_ROLES,
    has_any_role,
    is_admin_role,
    is_staff_role,
    normalize_role,
)

permission_logger = logging.getLogger("permissions")

logger = logging.getLogger(__name__)



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

# =============================================================================
# Phase 7: Object-Level Permission — OWASP API3:2023 BOLA/IDOR Prevention
# =============================================================================


class IsOwnerOrAdmin(BasePermission):
    """
    Object-level permission: owner or admin/staff can access.

    Prevents Broken Object Level Authorization (BOLA/IDOR) per OWASP API3:2023.

    Usage (on a ViewSet):
        class MyViewSet(OwnershipViewSetMixin, ModelViewSet):
            permission_classes = [IsAuthenticatedAndActive, IsOwnerOrAdmin]
            owner_field = "user"

    The view must also inherit OwnershipViewSetMixin to auto-invoke
    check_object_permissions on every detail action.
    """

    message = "You do not have permission to access this resource."
    owner_field: str = "user"

    def has_permission(self, request, view) -> bool:
        """Request-level: must be authenticated and active."""
        user = _get_user(request)
        return _is_authenticated_user(user)

    def has_object_permission(self, request, view, obj) -> bool:
        """
        Object-level: owner or admin/staff.

        Resolves owner via view.owner_field (default 'user').
        Supports FK chains: 'vendor__user', 'profile__user', etc.
        """
        user = _get_user(request)
        if not _is_authenticated_user(user):
            return False

        role = _get_role(user)
        if is_admin_role(role) or is_staff_role(role):
            return True

        field = getattr(view, "owner_field", self.owner_field)
        try:
            owner = obj
            for part in field.split("__"):
                owner = getattr(owner, part, None)
                if owner is None:
                    break
        except Exception:
            owner = None

        granted = owner is not None and owner == user
        if not granted:
            permission_logger.warning(
                "IsOwnerOrAdmin DENIED: user=%s on %s pk=%s action=%s",
                getattr(user, "id", "?"),
                type(obj).__name__,
                getattr(obj, "pk", "?"),
                getattr(view, "action", "?"),
            )
        return granted


class OwnershipViewSetMixin:
    """
    ViewSet mixin: auto-calls check_object_permissions on all detail actions.

    Eliminates the risk of forgetting to enforce object-level permissions in
    custom retrieve/update/destroy methods.

    Inherit BEFORE ModelViewSet:
        class ProductViewSet(OwnershipViewSetMixin, ModelViewSet):
            permission_classes = [IsAuthenticatedAndActive, IsOwnerOrAdmin]
            owner_field = "vendor__user"
    """

    _DETAIL_ACTIONS: frozenset = frozenset({
        "retrieve", "update", "partial_update", "destroy",
        "download", "revoke", "cancel", "approve", "reject",
    })

    def get_object(self):
        """Guarantees check_object_permissions for every detail action."""
        obj = super().get_object()
        action = getattr(self, "action", None)
        if action in self._DETAIL_ACTIONS:
            self.check_object_permissions(self.request, obj)
        return obj


class IsProductOwner(BasePermission):
    """Enforces strict owner-level access controls on product resources.
    Verifies that the authenticated user holds a valid VendorProfile and is the
    exclusive owner of the referenced Product resource. Denies access by default
    to prevent horizontal privilege escalation.
    Object-level permission enforcing that the executing user is the
    associated product designer/vendor owner.
    """

    message = "You do not have permission to modify this product."

    owner_field: str = "user"   
    def has_object_permission(self, request, view, obj) -> bool:
        """Verifies direct product ownership against the user's VendorProfile."""
        user = _get_user(request)
        if not _is_authenticated_user(user):
            return False
        # Check reverse relation helper for VendorProfile
        vendor_profile = getattr(request.user, "vendor_profile", None) or \
                         getattr(request.user, "vendor", None) or \
                         getattr(request.user, "vendor__profile", None)
                         
        if not vendor_profile:
            permission_logger.warning(
                "Access Denied: User %s lacks a valid VendorProfile.", request.user.email
            )
            return False
        
        # Determine resource type and check owner
        if isinstance(obj, Product):
            is_owner = obj.vendor == vendor_profile
        elif hasattr(obj, "product") and isinstance(obj.product, Product):
            is_owner = obj.product.vendor == vendor_profile
        else:
            is_owner = False
            
        if not is_owner:
            permission_logger.warning(
                "IDOR Prevention: User %s (Vendor %s) attempted to access unauthorized resource %s owned by Vendor %s",
                request.user.email, vendor_profile.id, obj.id, getattr(obj, 'vendor_id', 'unknown')
            )
            raise PermissionDenied("You do not have administrative clearance permission to access this product resource.")
            
        return is_owner




class IsProductOwner(permissions.BasePermission):
    """Enforces strict owner-level access controls on product resources.
    
    Verifies that the authenticated user holds a valid VendorProfile and is the
    exclusive owner of the referenced Product resource. Denies access by default
    to prevent horizontal privilege escalation.
    """

    def has_permission(self, request, view) -> bool:
        # Enforce that the user is authenticated and holds a provisioned vendor profile
        if not (request.user and request.user.is_authenticated):
            return False
        
        # Check reverse relation helper for VendorProfile
        vendor_profile = getattr(request.user, "vendor_profile", None)
        if not vendor_profile:
            logger.warning(
                "Access Denied: User %s lacks a valid VendorProfile.", request.user.email
            )
            return False
        
        return True

    def has_object_permission(self, request, view, obj) -> bool:
        """Verifies direct product ownership against the user's VendorProfile."""
        vendor_profile = getattr(request.user, "vendor_profile", None)
        if not vendor_profile:
            return False
            
        # Determine resource type and check owner
        if isinstance(obj, Product):
            is_owner = obj.vendor == vendor_profile
        elif hasattr(obj, "product") and isinstance(obj.product, Product):
            is_owner = obj.product.vendor == vendor_profile
        else:
            is_owner = False
            
        if not is_owner:
            logger.warning(
                "IDOR Prevention: User %s (Vendor %s) attempted to access unauthorized resource %s owned by Vendor %s",
                request.user.email, vendor_profile.id, obj.id, getattr(obj, 'vendor_id', 'unknown')
            )
            raise PermissionDenied("You do not have administrative clearance for this product resource.")
            
        return is_owner
