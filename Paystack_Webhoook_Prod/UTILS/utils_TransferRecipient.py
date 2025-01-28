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
def fetch_user_and_vendor(user):
    """
    This function retrieves the user and the vendor if user is a vendor.
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

    return user_obj, vendor_obj, None






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

















































































































































# +++++++++++++++++++    OLD ONE +++++++++++++++++++++++++++++++++++++++++++++++++++++++++



# from vendor.models import Vendor
# from userauths.models import  User
# from decimal import Decimal
# from django.db import transaction
# from django.conf import settings
# import logging
# import requests
# import json
# from rest_framework.response import Response
# from rest_framework import status






# # Get logger for application
# application_logger = logging.getLogger('application')
# # Get logger for paystack
# paystack_logger = logging.getLogger('paystack')






# def create_transfer_recipient(recipient_data):
#     '''
#     This function is used to create a paystack transfer recipient.
#     '''
#     url = "https://api.paystack.co/transferrecipient"
#     headers = {
#             "Authorization": "Bearer "+ settings.PAYSTACK_SECRET_KEY,
#             'Content-Type': 'application/json'
#         }
#     try:
#         res = requests.post(url, data=json.dumps(recipient_data), headers=headers)
#         res.raise_for_status()
#         return res.json()
#     except requests.exceptions.RequestException as e:
#         paystack_logger.error(f"Failed to create transfer recipient, paystack error: {e}")
#         return {"status": False, "message": f"Failed to create transfer recipient: {e}"}

# def update_transfer_recipient(recipient_code, recipient_data):
#     '''
#     This function is used to update a paystack transfer recipient.
#     '''
#     url = f"https://api.paystack.co/transferrecipient/{recipient_code}"
#     headers = {
#             "Authorization": "Bearer "+ settings.PAYSTACK_SECRET_KEY,
#             'Content-Type': 'application/json'
#         }
#     try:
#          res = requests.put(url, data=json.dumps(recipient_data), headers=headers)
#          res.raise_for_status()
#          return res.json()
#     except requests.exceptions.RequestException as e:
#          paystack_logger.error(f"Failed to update transfer recipient, paystack error: {e}")
#          return {"status": False, "message": f"Failed to update transfer recipient: {e}"}

# def delete_transfer_recipient(recipient_code):
#     '''
#     This function is used to delete a paystack transfer recipient.
#     '''
#     url = f"https://api.paystack.co/transferrecipient/{recipient_code}"
#     headers = {
#             "Authorization": "Bearer "+ settings.PAYSTACK_SECRET_KEY,
#         }
#     try:
#         res = requests.delete(url, headers=headers)
#         res.raise_for_status()
#         return res.json()
#     except requests.exceptions.RequestException as e:
#         paystack_logger.error(f"Failed to delete transfer recipient, paystack error: {e}")
#         return {"status": False, "message": f"Failed to delete transfer recipient: {e}"}


# def validate_bank_details(data):
#     """
#     Validates that the required fields for bank details is present.
#     """
#     account_number = data.get('account_number')
#     account_full_name = data.get('account_full_name')
#     bank_name = data.get('bank_name')
#     bank_code = data.get('bank_code')

#     if not all([account_number, account_full_name, bank_name, bank_code]):
#          return "All fields are required: 'account_number', 'account_full_name', 'bank_name', and 'bank_code'."
    
#     try:
#          int(account_number)
#     except ValueError:
#         return "Account number must contain only numbers."

#     return None # return none if there is no error

# def fetch_user_and_vendor(user):
#     """
#     This function retrieves the user and the vendor if user is a vendor.
#     """
#     try:
#         user_obj = User.objects.get(pk=user.pk)
#     except User.DoesNotExist:
#         application_logger.error(f"User with id {user.pk} does not exist")
#         return None, None,  "User not found"
    
#     vendor_obj = None
#     if user_obj.role == 'vendor':
#           try:
#                 vendor_obj = Vendor.objects.get(user=user_obj)
#           except Vendor.DoesNotExist:
#                 application_logger.error(f"Vendor profile not found for user: {user_obj.email}")
#                 return user_obj, None, "Vendor profile not found"

#     return user_obj, vendor_obj, None