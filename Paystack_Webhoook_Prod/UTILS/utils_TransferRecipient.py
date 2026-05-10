from vendor.models import Vendor
from userauths.models import  User
from decimal import Decimal
from django.db import transaction
from django.conf import settings
import logging
import requests
import json
from rest_framework.response import Response
from rest_framework import status
from rest_framework.exceptions import PermissionDenied, NotFound

# Get logger for application
application_logger = logging.getLogger('application')
# Get logger for paystack
paystack_logger = logging.getLogger('paystack')

def create_transfer_recipient(recipient_data):
    '''
    This function is used to create a paystack transfer recipient.
    '''
    url = "https://api.paystack.co/transferrecipient"
    headers = {
            "Authorization": "Bearer "+ settings.PAYSTACK_SECRET_KEY,
            'Content-Type': 'application/json'
        }
    try:
        res = requests.post(url, data=json.dumps(recipient_data), headers=headers)
        res.raise_for_status()
        return res.json()
    except requests.exceptions.RequestException as e:
        paystack_logger.error(f"Failed to create transfer recipient, paystack error: {e}")
        return {"status": False, "message": f"Failed to create transfer recipient: {e}"}

def update_transfer_recipient(recipient_code, recipient_data):
    '''
    This function is used to update a paystack transfer recipient.
    '''
    url = f"https://api.paystack.co/transferrecipient/{recipient_code}"
    headers = {
            "Authorization": "Bearer "+ settings.PAYSTACK_SECRET_KEY,
            'Content-Type': 'application/json'
        }
    try:
         res = requests.put(url, data=json.dumps(recipient_data), headers=headers)
         res.raise_for_status()
         return res.json()
    except requests.exceptions.RequestException as e:
         paystack_logger.error(f"Failed to update transfer recipient, paystack error: {e}")
         return {"status": False, "message": f"Failed to update transfer recipient: {e}"}

def delete_transfer_recipient(recipient_code):
    '''
    This function is used to delete a paystack transfer recipient.
    '''
    url = f"https://api.paystack.co/transferrecipient/{recipient_code}"
    headers = {
            "Authorization": "Bearer "+ settings.PAYSTACK_SECRET_KEY,
        }
    try:
        res = requests.delete(url, headers=headers)
        res.raise_for_status()
        return res.json()
    except requests.exceptions.RequestException as e:
        paystack_logger.error(f"Failed to delete transfer recipient, paystack error: {e}")
        return {"status": False, "message": f"Failed to delete transfer recipient: {e}"}
def validate_bank_details(data):
    """
    Validates that the required fields for bank details is present.
    """
    account_number = data.get('account_number')
    account_full_name = data.get('account_full_name')
    bank_name = data.get('bank_name')
    bank_code = data.get('bank_code')

    if not all([account_number, account_full_name, bank_name, bank_code]):
         return "All fields are required: 'account_number', 'account_full_name', 'bank_name', and 'bank_code'."
    
    try:
         int(account_number)
    except ValueError:
        return "Account number must contain only numbers."

    return None # return none if there is no error






def fetch_transfer_recipient(recipient_code):
    '''
    This function is used to fetch a paystack transfer recipient.
    '''
    url = f"https://api.paystack.co/transferrecipient/{recipient_code}"
    headers = {
            "Authorization": "Bearer "+ settings.PAYSTACK_SECRET_KEY,
        }
    try:
        res = requests.get(url, headers=headers)
        res.raise_for_status()
        return res.json()
    except requests.exceptions.RequestException as e:
        paystack_logger.error(f"Failed to fetch transfer recipient, paystack error: {e}")
        return {"status": False, "message": f"Failed to fetch transfer recipient: {e}"}






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
      application_logger.error(f"Permission denied: Vendor {vendor_obj.user.email} is not the owner of object {obj}")
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



































































































