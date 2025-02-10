from rest_framework import permissions
from userauths.models import User
from vendor.models import Vendor
import logging

application_logger = logging.getLogger('application')


class IsVendor(permissions.BasePermission):
    """
    Allows access only to vendors.
    """

    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == 'vendor'


class VendorIsOwner(permissions.BasePermission):
    """
    Allows access only to the vendor who owns the object.

    This permission assumes the object has a 'vendor' attribute
    that is either a Vendor object OR a User object (in the case
    where the vendor is directly linked via user relationship).
    It also handles the case when 'user' is used instead of 'vendor'.
    """

    def has_object_permission(self, request, view, obj):
        if not request.user.is_authenticated:
            return False

        try:
            vendor = Vendor.objects.get(user=request.user)
        except Vendor.DoesNotExist:
            application_logger.error(f"Vendor profile not found for user: {request.user.email}")
            return False

        if hasattr(obj, 'vendor'):
            # Case 1: Object has a 'vendor' attribute which is a Vendor object
            if isinstance(obj.vendor, Vendor):
                return obj.vendor == vendor
            # Case 2: Object has a 'vendor' attribute which is a User object
            elif isinstance(obj.vendor, User):
                return obj.vendor == request.user  # compare user directly
            else:
                application_logger.error(f"Object vendor attribute has unexpected type: {type(obj.vendor)}")
                return False  # Handle unexpected type for vendor

        elif hasattr(obj, 'user'):
            #Case 3: if the object has a user, which is only for vendor
            return obj.user == request.user
        else:
            application_logger.error(f"Object missing vendor or user attribute")
            return False

class IsClient(permissions.BasePermission):
    """
    Allows access only to clients.
    """
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == 'client'


class ClientIsOwner(permissions.BasePermission):
    """
    Allows access only to the client who owns the object.
    Assumes the object has a 'user' attribute referencing the User model.
    """
    def has_object_permission(self, request, view, obj):
        if not request.user.is_authenticated:
            return False

        if hasattr(obj, 'user'):
            return obj.user == request.user  # Direct user comparison
        else:
            application_logger.error(f"Object missing user attribute for client ownership check.")
            return False