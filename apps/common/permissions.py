from rest_framework import permissions
import logging

logger = logging.getLogger('application')

class IsVendor(permissions.BasePermission):
    """
    Allows access only to users with 'vendor' role.
    """
    message = "You do not have permission as you are not a vendor."

    def has_permission(self, request, view):
        try:
            return bool(request.user and request.user.is_authenticated and request.user.role == 'vendor')
        except Exception as e:
            logger.error(f"Error in IsVendor permission: {str(e)}")
            return False

class IsClient(permissions.BasePermission):
    """
    Allows access only to users with 'client' role.
    """
    message = "You do not have permission as you are not a client."

    def has_permission(self, request, view):
        try:
            return bool(request.user and request.user.is_authenticated and request.user.role == 'client')
        except Exception as e:
            logger.error(f"Error in IsClient permission: {str(e)}")
            return False

class IsStaff(permissions.BasePermission):
    """
    Allows access only to users with 'staff' role.
    """
    message = "You do not have permission as you are not staff."

    def has_permission(self, request, view):
        try:
            return bool(request.user and request.user.is_authenticated and request.user.role == 'staff')
        except Exception as e:
            logger.error(f"Error in IsStaff permission: {str(e)}")
            return False

class IsAdmin(permissions.BasePermission):
    """
    Allows access only to users with 'admin' role.
    """
    message = "You do not have permission as you are not an admin."

    def has_permission(self, request, view):
        try:
            return bool(request.user and request.user.is_authenticated and request.user.role == 'admin')
        except Exception as e:
            logger.error(f"Error in IsAdmin permission: {str(e)}")
            return False

class IsOwner(permissions.BasePermission):
    """
    Allows access only to owners of the object.
    Checks 'user', 'vendor.user', or 'product.vendor.user' attrs.
    """
    message = "You do not have permission to access this object as you are not the owner."

    def has_object_permission(self, request, view, obj):
        try:
            if not request.user.is_authenticated:
                return False
                
            # Direct user ownership
            if hasattr(obj, 'user'):
                return obj.user == request.user
            
            # Vendor ownership
            if hasattr(obj, 'vendor'):
                return obj.vendor.user == request.user
                
            # Default fallback
            return getattr(obj, 'owner', None) == request.user
            
        except Exception as e:
            logger.error(f"Error in IsOwner permission: {str(e)}")
            return False
