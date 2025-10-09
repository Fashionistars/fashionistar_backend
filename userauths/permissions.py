# userauth/permissions.py

from rest_framework import permissions
from vendor.models import Vendor
import logging

# Get logger for application
application_logger = logging.getLogger('application')

class IsVendor(permissions.BasePermission):
    """
    Allows view-level access only to users with the 'vendor' role.
    Used for actions like creating a new product where no object exists yet.
    """
    message = "You do not have permission to perform this action as you are not a vendor."

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.role == 'vendor')

class IsClient(permissions.BasePermission):
    """
    Allows view-level access only to users with the 'client' role.
    """
    message = "You do not have permission to perform this action as you are not a client."

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.role == 'client')

class IsOwner(permissions.BasePermission):
    """
    A unified object-level permission to only allow owners of an object to access it.
    This class intelligently checks for ownership based on the user's role (vendor or client).
    """
    message = "You do not have permission to access this object as you are not the owner."

    def has_object_permission(self, request, view, obj):
        # The user must be authenticated.
        if not request.user or not request.user.is_authenticated:
            return False

        # --- Vendor Ownership Logic ---
        if request.user.role == 'vendor':
            try:
                # Get the vendor profile associated with the requesting user.
                vendor = request.user.vendor_profile
            except Vendor.DoesNotExist:
                application_logger.error(f"Permission check failed: No vendor profile found for user: {request.user.email}")
                return False

            # Check 1: The object has a direct 'vendor' foreign key (e.g., Product, Coupon).
            if hasattr(obj, 'vendor'):
                return obj.vendor == vendor

            # Check 2: The object has a 'user' foreign key that belongs to the vendor (e.g., Profile).
            if hasattr(obj, 'user'):
                return obj.user == vendor.user

            application_logger.warning(f"IsOwner check failed for vendor {vendor.name}: Object {obj} has no 'vendor' or 'user' attribute for ownership check.")
            return False

        # --- Client Ownership Logic ---
        elif request.user.role == 'client':
            # Check: The object has a 'user' foreign key matching the requesting client.
            if hasattr(obj, 'user'):
                return obj.user == request.user

            application_logger.warning(f"IsOwner check failed for client {request.user.email}: Object {obj} has no 'user' attribute for ownership check.")
            return False
            
        return False