from rest_framework import permissions
import logging

logger = logging.getLogger('application')

class IsTokenValid(permissions.BasePermission):
    """
    Custom permission to check if the user's token is valid.
    """
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated

class IsVendorUser(permissions.BasePermission):
    """
    Allows access only to users with 'vendor' role.
    """
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.role == 'vendor')

class IsClientUser(permissions.BasePermission):
    """
    Allows access only to users with 'client' role.
    """
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.role == 'client')