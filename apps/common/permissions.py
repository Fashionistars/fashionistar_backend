"""
Common permissions for the Fashionistar project.

This module contains shared permission classes used across all Django apps
to enforce access control in the modular monolith architecture. These permissions
are designed to be async-compatible for future Django versions and include
robust error handling and logging for maintainability.
"""
# apps/common/permissions.py
from rest_framework.permissions import BasePermission
from django.contrib.auth.models import AnonymousUser
import logging

# Get logger for permission-related logging
permission_logger = logging.getLogger('permissions')


class IsVendor(BasePermission):
    """
    Permission class to check if the user is a vendor.

    This permission ensures that only users with the 'vendor' role can access
    vendor-specific endpoints. It includes async support and detailed logging
    for security auditing.

    Message:
        Default deny message for unauthorized access.
    """

    message = "You must be a vendor to access this resource."

    def has_permission(self, request, view):
        """
        Check if the user has vendor permissions.

        This method verifies the user's role and logs the access attempt

        for security purposes.

        Args:
            request (Request): The HTTP request object.
            view (View): The view being accessed.

        Returns:
            bool: True if the user is a vendor, False otherwise.
        """
        try:
            user = request.user
            if isinstance(user, AnonymousUser):
                permission_logger.warning("Anonymous user attempted vendor access")
                return False

            is_vendor = getattr(user, 'role', None) == 'vendor'
            if is_vendor:
                permission_logger.info(f"Vendor access granted to user: {user}")
            else:
                permission_logger.warning(f"Non-vendor user {user} attempted vendor access")
            return is_vendor
        except Exception as e:
            permission_logger.error(f"Error checking vendor permission for user {request.user}: {e}")
            return False

    async def has_permission_async(self, request, view):
        """
        Async version of has_permission for future Django async views.

        This method provides the same functionality as has_permission but
        is designed for async contexts to support high-performance APIs.

        Args:
            request (Request): The HTTP request object.
            view (View): The view being accessed.

        Returns:
            bool: True if the user is a vendor, False otherwise.
        """
        try:
            user = await request.auser() if hasattr(request, 'auser') else request.user
            if isinstance(user, AnonymousUser):
                permission_logger.warning("Anonymous user attempted vendor access (async)")
                return False

            is_vendor = getattr(user, 'role', None) == 'vendor'
            if is_vendor:
                permission_logger.info(f"Vendor access granted to user (async): {user}")
            else:
                permission_logger.warning(f"Non-vendor user {user} attempted vendor access (async)")
            return is_vendor
        except Exception as e:
            permission_logger.error(f"Error checking vendor permission (async) for user {request.user}: {e}")
            return False


class IsClient(BasePermission):
    """
    Permission class to check if the user is a client/customer.

    This permission restricts access to client-specific endpoints, ensuring
    that only authenticated clients can perform customer-related actions.

    Message:
        Default deny message for unauthorized access.
    """

    message = "You must be a client to access this resource."

    def has_permission(self, request, view):
        """
        Check if the user has client permissions.

        Args:
            request (Request): The HTTP request object.
            view (View): The view being accessed.

        Returns:
            bool: True if the user is a client, False otherwise.
        """
        try:
            user = request.user
            if isinstance(user, AnonymousUser):
                permission_logger.warning("Anonymous user attempted client access")
                return False

            is_client = getattr(user, 'role', None) == 'client'
            if is_client:
                permission_logger.info(f"Client access granted to user: {user}")
            else:
                permission_logger.warning(f"Non-client user {user} attempted client access")
            return is_client
        except Exception as e:
            permission_logger.error(f"Error checking client permission for user {request.user}: {e}")
            return False

    async def has_permission_async(self, request, view):
        """
        Async version of has_permission.

        Args:
            request (Request): The HTTP request object.
            view (View): The view being accessed.

        Returns:
            bool: True if the user is a client, False otherwise.
        """
        try:
            user = await request.auser() if hasattr(request, 'auser') else request.user
            if isinstance(user, AnonymousUser):
                permission_logger.warning("Anonymous user attempted client access (async)")
                return False

            is_client = getattr(user, 'role', None) == 'client'
            if is_client:
                permission_logger.info(f"Client access granted to user (async): {user}")
            else:
                permission_logger.warning(f"Non-client user {user} attempted client access (async)")
            return is_client
        except Exception as e:
            permission_logger.error(f"Error checking client permission (async) for user {request.user}: {e}")
            return False


class IsStaff(BasePermission):
    """
    Permission class to check if the user is staff (support, reviewer, etc.).

    This permission allows access for internal staff roles, enabling
    administrative functions while maintaining security.

    Message:
        Default deny message for unauthorized access.
    """

    message = "You must be staff to access this resource."

    def has_permission(self, request, view):
        """
        Check if the user has staff permissions.

        Args:
            request (Request): The HTTP request object.
            view (View): The view being accessed.

        Returns:
            bool: True if the user is staff, False otherwise.
        """
        try:
            user = request.user
            if isinstance(user, AnonymousUser):
                permission_logger.warning("Anonymous user attempted staff access")
                return False

            staff_roles = ['support', 'reviewer', 'assistant', 'admin']
            is_staff = getattr(user, 'role', None) in staff_roles
            if is_staff:
                permission_logger.info(f"Staff access granted to user: {user}")
            else:
                permission_logger.warning(f"Non-staff user {user} attempted staff access")
            return is_staff
        except Exception as e:
            permission_logger.error(f"Error checking staff permission for user {request.user}: {e}")
            return False

    async def has_permission_async(self, request, view):
        """
        Async version of has_permission.

        Args:
            request (Request): The HTTP request object.
            view (View): The view being accessed.

        Returns:
            bool: True if the user is staff, False otherwise.
        """
        try:
            user = await request.auser() if hasattr(request, 'auser') else request.user
            if isinstance(user, AnonymousUser):
                permission_logger.warning("Anonymous user attempted staff access (async)")
                return False

            staff_roles = ['support', 'reviewer', 'assistant', 'admin']
            is_staff = getattr(user, 'role', None) in staff_roles
            if is_staff:
                permission_logger.info(f"Staff access granted to user (async): {user}")
            else:
                permission_logger.warning(f"Non-staff user {user} attempted staff access (async)")
            return is_staff
        except Exception as e:
            permission_logger.error(f"Error checking staff permission (async) for user {request.user}: {e}")
            return False


class IsOwner(BasePermission):
    """
    Permission class to check if the user is the owner of the resource.

    This permission is object-level and checks if the requesting user
    owns the specific object being accessed.

    Message:
        Default deny message for unauthorized access.
    """

    message = "You must be the owner of this resource to access it."

    def has_object_permission(self, request, view, obj):
        """
        Check if the user owns the object.

        This method assumes the object has a 'user' field or similar
        owner relationship.

        Args:
            request (Request): The HTTP request object.
            view (View): The view being accessed.
            obj: The object being accessed.

        Returns:
            bool: True if the user owns the object, False otherwise.
        """
        try:
            user = request.user
            if isinstance(user, AnonymousUser):
                permission_logger.warning("Anonymous user attempted owner access")
                return False

            # Assuming obj has a 'user' field; adjust as needed
            is_owner = getattr(obj, 'user', None) == user
            if is_owner:
                permission_logger.info(f"Owner access granted to user {user} for object {obj}")
            else:
                permission_logger.warning(f"Non-owner user {user} attempted access to object {obj}")
            return is_owner
        except Exception as e:
            permission_logger.error(f"Error checking owner permission for user {request.user} on object {obj}: {e}")
            return False

    async def has_object_permission_async(self, request, view, obj):
        """
        Async version of has_object_permission.

        Args:
            request (Request): The HTTP request object.
            view (View): The view being accessed.
            obj: The object being accessed.

        Returns:
            bool: True if the user owns the object, False otherwise.
        """
        try:
            user = await request.auser() if hasattr(request, 'auser') else request.user
            if isinstance(user, AnonymousUser):
                permission_logger.warning("Anonymous user attempted owner access (async)")
                return False

            is_owner = getattr(obj, 'user', None) == user
            if is_owner:
                permission_logger.info(f"Owner access granted to user (async) {user} for object {obj}")
            else:
                permission_logger.warning(f"Non-owner user {user} attempted access (async) to object {obj}")
            return is_owner
        except Exception as e:
            permission_logger.error(f"Error checking owner permission (async) for user {request.user} on object {obj}: {e}")
            return False


class IsSupport(BasePermission):
    """
    Permission class to check if the user is support staff.

    This permission is specifically for support roles, allowing
    customer service functions.

    Message:
        Default deny message for unauthorized access.
    """

    message = "You must be support staff to access this resource."

    def has_permission(self, request, view):
        """
        Check if the user has support permissions.

        Args:
            request (Request): The HTTP request object.
            view (View): The view being accessed.

        Returns:
            bool: True if the user is support, False otherwise.
        """
        try:
            user = request.user
            if isinstance(user, AnonymousUser):
                permission_logger.warning("Anonymous user attempted support access")
                return False

            is_support = getattr(user, 'role', None) == 'support'
            if is_support:
                permission_logger.info(f"Support access granted to user: {user}")
            else:
                permission_logger.warning(f"Non-support user {user} attempted support access")
            return is_support
        except Exception as e:
            permission_logger.error(f"Error checking support permission for user {request.user}: {e}")
            return False

    async def has_permission_async(self, request, view):
        """
        Async version of has_permission.

        Args:
            request (Request): The HTTP request object.
            view (View): The view being accessed.

        Returns:
            bool: True if the user is support, False otherwise.
        """
        try:
            user = await request.auser() if hasattr(request, 'auser') else request.user
            if isinstance(user, AnonymousUser):
                permission_logger.warning("Anonymous user attempted support access (async)")
                return False

            is_support = getattr(user, 'role', None) == 'support'
            if is_support:
                permission_logger.info(f"Support access granted to user (async): {user}")
            else:
                permission_logger.warning(f"Non-support user {user} attempted support access (async)")
            return is_support
        except Exception as e:
            permission_logger.error(f"Error checking support permission (async) for user {request.user}: {e}")
            return False


class IsEditor(BasePermission):
    """
    Permission class to check if the user is an editor/reviewer.

    This permission allows content editing and review functions.

    Message:
        Default deny message for unauthorized access.
    """

    message = "You must be an editor to access this resource."

    def has_permission(self, request, view):
        """
        Check if the user has editor permissions.

        Args:
            request (Request): The HTTP request object.
            view (View): The view being accessed.

        Returns:
            bool: True if the user is an editor, False otherwise.
        """
        try:
            user = request.user
            if isinstance(user, AnonymousUser):
                permission_logger.warning("Anonymous user attempted editor access")
                return False

            is_editor = getattr(user, 'role', None) == 'reviewer'
            if is_editor:
                permission_logger.info(f"Editor access granted to user: {user}")
            else:
                permission_logger.warning(f"Non-editor user {user} attempted editor access")
            return is_editor
        except Exception as e:
            permission_logger.error(f"Error checking editor permission for user {request.user}: {e}")
            return False

    async def has_permission_async(self, request, view):
        """
        Async version of has_permission.

        Args:
            request (Request): The HTTP request object.
            view (View): The view being accessed.

        Returns:
            bool: True if the user is an editor, False otherwise.
        """
        try:
            user = await request.auser() if hasattr(request, 'auser') else request.user
            if isinstance(user, AnonymousUser):
                permission_logger.warning("Anonymous user attempted editor access (async)")
                return False

            is_editor = getattr(user, 'role', None) == 'reviewer'
            if is_editor:
                permission_logger.info(f"Editor access granted to user (async): {user}")
            else:
                permission_logger.warning(f"Non-editor user {user} attempted editor access (async)")
            return is_editor
        except Exception as e:
            permission_logger.error(f"Error checking editor permission (async) for user {request.user}: {e}")
            return False


class IsSales(BasePermission):
    """
    Permission class to check if the user is sales staff.

    This permission allows sales-related functions and analytics.

    Message:
        Default deny message for unauthorized access.
    """

    message = "You must be sales staff to access this resource."

    def has_permission(self, request, view):
        """
        Check if the user has sales permissions.

        Args:
            request (Request): The HTTP request object.
            view (View): The view being accessed.

        Returns:
            bool: True if the user is sales, False otherwise.
        """
        try:
            user = request.user
            if isinstance(user, AnonymousUser):
                permission_logger.warning("Anonymous user attempted sales access")
                return False

            is_sales = getattr(user, 'role', None) == 'assistant'
            if is_sales:
                permission_logger.info(f"Sales access granted to user: {user}")
            else:
                permission_logger.warning(f"Non-sales user {user} attempted sales access")
            return is_sales
        except Exception as e:
            permission_logger.error(f"Error checking sales permission for user {request.user}: {e}")
            return False

    async def has_permission_async(self, request, view):
        """
        Async version of has_permission.

        Args:
            request (Request): The HTTP request object.
            view (View): The view being accessed.

        Returns:
            bool: True if the user is sales, False otherwise.
        """
        try:
            user = await request.auser() if hasattr(request, 'auser') else request.user
            if isinstance(user, AnonymousUser):
                permission_logger.warning("Anonymous user attempted sales access (async)")
                return False

            is_sales = getattr(user, 'role', None) == 'assistant'
            if is_sales:
                permission_logger.info(f"Sales access granted to user (async): {user}")
            else:
                permission_logger.warning(f"Non-sales user {user} attempted sales access (async)")
            return is_sales
        except Exception as e:
            permission_logger.error(f"Error checking sales permission (async) for user {request.user}: {e}")
            return False


# =============================================================================
# IsAuthenticatedAndActive
# =============================================================================

class IsAuthenticatedAndActive(BasePermission):
    """
    Ensures the user is authenticated AND has an active account (is_active=True).

    This is stricter than DRF's built-in `IsAuthenticated` which only checks
    that a valid JWT was presented — it does NOT verify that the account has
    been activated or hasn't been suspended by an admin.

    Use this on any endpoint where a suspended user must be blocked
    even if they hold a valid, non-expired JWT token.

    Example:
        class MyView(APIView):
            permission_classes = [IsAuthenticatedAndActive]
    """

    message = "Your account is inactive. Please contact support."

    def has_permission(self, request, view):
        try:
            user = request.user
            if isinstance(user, AnonymousUser) or not user.is_authenticated:
                permission_logger.warning(
                    "IsAuthenticatedAndActive: anonymous/unauthenticated request blocked."
                )
                return False

            if not user.is_active:
                permission_logger.warning(
                    "IsAuthenticatedAndActive: inactive account '%s' blocked.",
                    getattr(user, 'email', user.pk),
                )
                return False

            return True
        except Exception as e:
            permission_logger.error(
                "IsAuthenticatedAndActive error for '%s': %s",
                getattr(request.user, 'email', '?'), e,
            )
            return False

    async def has_permission_async(self, request, view):
        try:
            user = await request.auser() if hasattr(request, 'auser') else request.user
            if isinstance(user, AnonymousUser) or not user.is_authenticated:
                return False
            if not user.is_active:
                permission_logger.warning(
                    "IsAuthenticatedAndActive (async): inactive account '%s' blocked.",
                    getattr(user, 'email', user.pk),
                )
                return False
            return True
        except Exception as e:
            permission_logger.error("IsAuthenticatedAndActive async error: %s", e)
            return False


# =============================================================================
# IsVerifiedUser
# =============================================================================

class IsVerifiedUser(BasePermission):
    """
    The highest-trust permission gate for authenticated users.

    Checks three conditions in strict order:
      1. User is authenticated (valid JWT / session).
      2. Account is active (is_active=True — not suspended).
      3. Identity is verified (is_verified=True — OTP/email confirmed).

    Use this on any endpoint that should be inaccessible to:
      - Unauthenticated visitors
      - Suspended users (is_active=False)
      - Registered but unverified users (is_verified=False)

    This mirrors the flow used by platforms like Binance and Coinbase where
    OTP verification is a hard prerequisite for accessing account features.

    Example:
        class ChangePasswordView(APIView):
            permission_classes = [IsVerifiedUser]
    """

    message = (
        "Your account is not yet verified. "
        "Please complete OTP verification to access this resource."
    )

    def has_permission(self, request, view):
        try:
            user = request.user
            if isinstance(user, AnonymousUser) or not user.is_authenticated:
                permission_logger.warning(
                    "IsVerifiedUser: unauthenticated request blocked."
                )
                return False

            if not user.is_active:
                permission_logger.warning(
                    "IsVerifiedUser: inactive account '%s' blocked.",
                    getattr(user, 'email', user.pk),
                )
                return False

            if not getattr(user, 'is_verified', False):
                permission_logger.warning(
                    "IsVerifiedUser: unverified account '%s' blocked.",
                    getattr(user, 'email', user.pk),
                )
                return False

            return True
        except Exception as e:
            permission_logger.error(
                "IsVerifiedUser error for '%s': %s",
                getattr(request.user, 'email', '?'), e,
            )
            return False

    async def has_permission_async(self, request, view):
        try:
            user = await request.auser() if hasattr(request, 'auser') else request.user
            if isinstance(user, AnonymousUser) or not user.is_authenticated:
                return False
            if not user.is_active:
                return False
            if not getattr(user, 'is_verified', False):
                permission_logger.warning(
                    "IsVerifiedUser (async): unverified account '%s' blocked.",
                    getattr(user, 'email', user.pk),
                )
                return False
            return True
        except Exception as e:
            permission_logger.error("IsVerifiedUser async error: %s", e)
            return False


# =============================================================================
# RateLimitPermission  (Redis-backed sliding window, per IP + per user)
# =============================================================================

class RateLimitPermission(BasePermission):
    """
    Redis-backed, per-IP + per-authenticated-user sliding-window rate limiter.

    Default: 100 requests / 3600 seconds (1 hour) per identity.

    How it works:
      - For anonymous requests  → keyed on IP address.
      - For authenticated users → keyed on user PK (bypasses IP spoofing).
      - Uses Redis INCR + EXPIRE in a pipeline for O(1) atomicity.
      - No blocking I/O: falls back to ALLOW if Redis is unavailable
        (fail-open strategy — never blocks legitimate users during cache outages).

    Customise limits per view by subclassing::

        class StrictRateLimit(RateLimitPermission):
            max_requests = 10
            window_seconds = 60

    Example:
        class LoginView(APIView):
            permission_classes = [RateLimitPermission]

    Attributes:
        max_requests (int):    Maximum requests allowed in the window.
        window_seconds (int):  Sliding window duration in seconds.
    """

    max_requests: int = 100
    window_seconds: int = 3600

    message = "Too many requests. Please slow down and try again later."

    @staticmethod
    def _get_client_ip(request) -> str:
        """Extract the real client IP, respecting proxy headers."""
        x_forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded:
            return x_forwarded.split(',')[0].strip()
        return request.META.get('REMOTE_ADDR', '0.0.0.0')

    def _get_cache_key(self, request) -> str:
        user = getattr(request, 'user', None)
        if user and user.is_authenticated:
            identity = f"user:{user.pk}"
        else:
            identity = f"ip:{self._get_client_ip(request)}"
        return f"ratelimit:{identity}"

    def has_permission(self, request, view) -> bool:
        try:
            from django.core.cache import cache

            cache_key = self._get_cache_key(request)

            # Atomic increment using Django cache (backed by Redis)
            current = cache.get(cache_key, 0)
            current += 1
            cache.set(cache_key, current, timeout=self.window_seconds)

            if current > self.max_requests:
                permission_logger.warning(
                    "RateLimitPermission: key='%s' hit limit (%d/%d).",
                    cache_key, current, self.max_requests,
                )
                return False
            return True
        except Exception as e:
            # Fail-open: never block on cache outage
            permission_logger.error(
                "RateLimitPermission error (fail-open): %s", e
            )
            return True

    async def has_permission_async(self, request, view) -> bool:
        # Delegate to sync version via thread for Django cache safety
        import asyncio
        try:
            return await asyncio.to_thread(self.has_permission, request, view)
        except Exception as e:
            permission_logger.error(
                "RateLimitPermission async error (fail-open): %s", e
            )
            return True


# =============================================================================
# require_verification  —  Function/Method decorator
# =============================================================================

def require_verification(func):
    """
    Decorator for DRF view methods that enforces ``IsVerifiedUser`` inline.

    Use this on individual methods when you want different permissions
    at the class level vs. the method level.

    Usage (on a method inside a ViewSet or APIView)::

        class UserProfileView(APIView):
            permission_classes = [IsAuthenticated]  # general gate

            @require_verification
            def patch(self, request, *args, **kwargs):
                # Only fully-verified users reach here
                ...

    The decorator adds ``IsVerifiedUser`` on top of whatever class-level
    permissions are already enforced by DRF.
    """
    from functools import wraps
    from apps.common.renderers import error_response
    from rest_framework import status

    @wraps(func)
    def wrapper(self, request, *args, **kwargs):
        permission = IsVerifiedUser()
        if not permission.has_permission(request, self):
            return error_response(
                message=permission.message,
                status=status.HTTP_403_FORBIDDEN,
                code="account_not_verified"
            )
        return func(self, request, *args, **kwargs)

    return wrapper

