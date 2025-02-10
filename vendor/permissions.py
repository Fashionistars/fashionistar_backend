from rest_framework import permissions
import logging

# Get logger for application
application_logger = logging.getLogger('application')

class IsVendor(permissions.BasePermission):
    """
    Allows access only to vendors.
    """

    def has_permission(self, request, view):
        """
        Check if the user is a vendor.
        """
        return bool(request.user and request.user.is_authenticated and request.user.role == 'vendor')


class VendorIsOwner(permissions.BasePermission):
    """
    Allows access only to vendors who own the object.
    """

    def has_object_permission(self, request, view, obj):
        """
        Check if the vendor owns the object.
        """
        if not request.user.is_authenticated or request.user.role != 'vendor':
            return False

        try:
            vendor = request.user.vendor_profile # Assuming a OneToOneField named vendor_profile exists
        except Vendor.DoesNotExist:
            application_logger.error(f"No vendor profile found for user: {request.user.email}")
            return False

        # Ownership check based on vendor foreign key
        if hasattr(obj, 'vendor'):
            return obj.vendor == vendor
        
        # Ownership check based on user foreign key and vendor
        if hasattr(obj, 'user'):
            return obj.user == vendor.user # Check if the obj.user is the same as the vendor's user
        
        application_logger.warning(f"Object {obj} does not have 'vendor' or 'user' attribute for ownership check.")
        return False


class IsClient(permissions.BasePermission):
    """
    Allows access only to clients.
    """

    def has_permission(self, request, view):
        """
        Check if the user is a client.
        """
        return bool(request.user and request.user.is_authenticated and request.user.role == 'client')


class ClientIsOwner(permissions.BasePermission):
    """
    Allows access only to clients who own the object.
    """

    def has_object_permission(self, request, view, obj):
        """
        Check if the client owns the object.
        """
        if not request.user.is_authenticated or request.user.role != 'client':
            return False

        if hasattr(obj, 'user'):
            return obj.user == request.user
        
        application_logger.warning(f"Object {obj} does not have 'user' attribute.")
        return False