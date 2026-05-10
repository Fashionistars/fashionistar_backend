from userauths.models import User
from vendor.models import Vendor
import logging
from rest_framework.response import Response
from rest_framework import status
from rest_framework.exceptions import PermissionDenied, NotFound

# Get logger for application
application_logger = logging.getLogger('application')

def fetch_user_and_vendor(user):
    """
    This function retrieves the user and the vendor if user is a vendor.

    Args:
       user (User): The user object from the request
    Returns:
        tuple: A tuple containing:
            - user_obj (User): The user object.
            - vendor_obj (Vendor): The vendor object if user is a vendor, else None
            - error (str): An error message, if any.
    """
    try:
        user_obj = User.objects.get(pk=user.pk)
    except User.DoesNotExist:
        application_logger.error(f"User with id {user.pk} does not exist")
        return None, None,  "User not found"
    
    vendor_obj = None
    if user_obj.role == 'vendor':
        try:
            vendor_obj = Vendor.objects.get(user=user_obj)
        except Vendor.DoesNotExist:
            application_logger.error(f"Vendor profile not found for user: {user_obj.email}")
            return user_obj, None, "Vendor profile not found"
    elif user_obj.role == 'client':
        pass # Return none for vendor if user is not a vendor
    else:
        application_logger.error(f"Invalid user role: {user_obj.role}")
        return user_obj, None, "Invalid user role"

    return user_obj, vendor_obj, None

def fetch_vendor(user):
    """
    Retrieves the vendor object if the user is a vendor.

    Returns:
        vendor_obj: Vendor object or None if the user is not a vendor
                     or vendor profile is missing
    """
    try:
        user_obj = User.objects.get(pk=user.pk)
    except User.DoesNotExist:
        application_logger.error(f"User with id {user.pk} does not exist")
        return None

    if user_obj.role != 'vendor':
        application_logger.error(f"User: {user_obj.email} is not a vendor")
        return None

    try:
        vendor_obj = Vendor.objects.get(user=user_obj)
    except Vendor.DoesNotExist:
        application_logger.error(f"Vendor profile not found for user: {user_obj.email}")
        return None

    return vendor_obj



def vendor_is_owner(vendor_obj, obj):
    """
    Checks if the provided vendor_obj is the owner of the given object.
    
    Raises:
        PermissionDenied: If vendor_obj is None or is not the owner of obj
    """
    if vendor_obj is None:
      application_logger.error(f"Permission denied: Vendor object is None.")
      raise PermissionDenied("You do not have permission to perform this action.")
      
    if hasattr(obj, 'vendor') and obj.vendor != vendor_obj:
      application_logger.error(f"Permission denied: VENDOR {vendor_obj.user.email} is not the owner of object {obj}")
      raise PermissionDenied("You do not have permission to perform this action.")

    if hasattr(obj, 'user') and hasattr(obj, 'vendor') and obj.vendor.user != vendor_obj.user:
          application_logger.error(f"Permission denied: User {vendor_obj.user.email} is not the owner of object {obj}")
          raise PermissionDenied("You do not have permission to perform this action.")
    
    if hasattr(obj, 'user') and not hasattr(obj, 'vendor') and obj.user != vendor_obj.user:
          application_logger.error(f"Permission denied: User {vendor_obj.user.email} is not the owner of object {obj}")
          raise PermissionDenied("You do not have permission to perform this action.")
    return True


def client_is_owner(user_obj, obj):
    """
    Checks if the provided user_obj is the owner of the given object.
    
    Raises:
         PermissionDenied: If user_obj is None or is not the owner of obj
    """
    if user_obj is None:
        application_logger.error("Permission denied: Client object is None.")
        raise PermissionDenied("You do not have permission to perform this action.")

    if hasattr(obj, 'user') and obj.user != user_obj:
        application_logger.error(f"Permission denied: User {user_obj.email} is not the owner of object {obj}")
        raise PermissionDenied("You do not have permission to perform this action.")

    return True












