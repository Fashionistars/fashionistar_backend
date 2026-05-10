from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.conf import settings
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from userauths.models import User, Profile
from decimal import Decimal
import json
import hashlib
import hmac

from Paystack_Webhoook_Prod.models import Transaction

from django.db import transaction
import logging

# Get logger for webhook
webhook_logger = logging.getLogger('webhook')
# Get logger for paystack
paystack_logger = logging.getLogger('paystack')
# Get logger for application
application_logger = logging.getLogger('application')


@csrf_exempt
def paystack_webhook_view(request):
    """
     This function handles all paystack webhook events.

        *   **URL:** `/api/paystack/webhook/`
        *   **Method:** `POST`
        *   **Authentication:** Webhook Signature verification
         *   **Request Body (JSON):** A JSON object from paystack.
          *   **Response (HTTP Status Code):**
              *   On success (HTTP 200 OK):
                     A 200 ok status code with no data
                *   On failure (HTTP 400 or 401):
                    The server will return a 400 status code if the header is missing or a 401 code if the signature verification fails.
    """
    if request.method == 'POST':
        # Get Paystack Signature
        paystack_signature = request.headers.get('X-Paystack-Signature')
        # Get webhook payload
        payload = request.body.decode('utf-8')
        try:
          if not paystack_signature:
            webhook_logger.error("Paystack signature is missing from header.")
            return HttpResponse(status=400)

            # Verify if request is from paystack
          if not verify_paystack_signature(payload, paystack_signature, settings.PAYSTACK_SECRET_KEY):
                webhook_logger.error(f"Invalid paystack signature received: {paystack_signature}")
                return HttpResponse(status=401)

           # Parse Payload
          try:
              payload_data = json.loads(payload)
          except json.JSONDecodeError as e:
              webhook_logger.error(f"Error decoding json payload from paystack webhook: {payload}, error: {e}")
              return HttpResponse(status=400)

           #Handle event
          handle_paystack_event(payload_data)
          return HttpResponse(status=200)
        except Exception as e:
            webhook_logger.error(f"An error occurred in paystack_webhook_view: {e}")
            return HttpResponse(status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    else:
        return HttpResponse(status=405)


def verify_paystack_signature(payload, signature, secret):
    '''
    This function is used to verify if the request is actually coming from paystack.
    '''
    try:
        key = bytes(secret, 'utf-8')
        hashed = hmac.new(key, payload.encode('utf-8'), hashlib.sha512).hexdigest()
        if hashed == signature:
            return True
        else:
             paystack_logger.warning("Paystack signature verification failed.")
             return False
    except Exception as e:
        paystack_logger.error(f"Error while verifying paystack signature: {e}")
        return False

@transaction.atomic
def handle_paystack_event(payload):
    '''
    This function handles all paystack events
    '''
    event = payload.get('event')
    try:
        if event == 'charge.success':
            handle_successful_charge(payload)
        elif event == 'charge.failed':
            handle_failed_charge(payload)
        elif event == "transfer.success":
            handle_successful_transfer(payload)
        elif event == "transfer.failed":
            handle_failed_transfer(payload)
        elif event == "transfer.reversed":
           handle_reversed_transfer(payload)
        else:
            webhook_logger.warning(f"Unhandled webhook event: {event}, payload is {payload}")
    except Exception as e:
          webhook_logger.error(f"An error occurred while handling the webhook event: {e}, event:{event}")


def handle_successful_charge(payload):
     '''
     This function is used to handle successful payments
     '''
     reference = payload['data']['reference']
     amount = payload['data']['amount']
     try:
          paystack_transaction = Transaction.objects.get(paystack_payment_reference=reference)
     except Transaction.DoesNotExist:
        webhook_logger.error(f"Transaction record does not exist for reference {reference}")
        return
     try:
         # If successful update the status and balance
            if paystack_transaction.status != 'success':
                paystack_transaction.status = 'success'
                paystack_transaction.save()
                # Find the profile of the user for the transaction and update the balance
                if paystack_transaction.user:
                    user_profile = Profile.objects.get(user=paystack_transaction.user)
                    user_profile.wallet_balance += Decimal(amount) / 100
                    user_profile.save()
                    webhook_logger.info(f"Updated user {paystack_transaction.user} balance, transaction reference: {reference}")
                elif paystack_transaction.vendor:
                    vendor_profile = Profile.objects.get(user=paystack_transaction.vendor.user)
                    vendor_profile.wallet_balance += Decimal(amount) / 100
                    vendor_profile.save()
                    webhook_logger.info(f"Updated vendor {paystack_transaction.vendor} balance, transaction reference: {reference}")
            else:
               webhook_logger.info(f"Payment already verified, reference:{reference}")
     except Exception as e:
            webhook_logger.error(f"An error occured in handle_successful_charge webhook handler, error is: {e}, for transaction reference is: {reference}")

def handle_failed_charge(payload):
      '''
        This function is used to handle failed payments
      '''
      reference = payload['data']['reference']
      status = payload['data']['status']
      try:
        try:
            paystack_transaction = Transaction.objects.get(paystack_payment_reference=reference)
        except Transaction.DoesNotExist:
             webhook_logger.error(f"Transaction record does not exist for reference: {reference}")
             return

         # If not successful, update the status
        with transaction.atomic():
            if paystack_transaction.status != status:
               paystack_transaction.status = status
               paystack_transaction.save()
               webhook_logger.info(f"Updated transaction status to: {status}, reference {reference}")
            else:
                webhook_logger.info(f"Status is already updated to: {status}, reference {reference}")
      except Exception as e:
            webhook_logger.error(f"An error occured in handle_failed_charge webhook handler, error is: {e}, for transaction reference is: {reference}")

def handle_successful_transfer(payload):
    '''
        This function is used to handle successful transfers
    '''
    transfer_code = payload['data']['transfer_code']
    try:
        try:
            paystack_transaction = Transaction.objects.get(paystack_transfer_code=transfer_code)
        except Transaction.DoesNotExist:
             webhook_logger.error(f"Transaction record does not exist for transfer code: {transfer_code}")
             return
            # If successful update the status
        with transaction.atomic():
            if paystack_transaction.status != 'success':
                paystack_transaction.status = 'success'
                paystack_transaction.save()
                webhook_logger.info(f"Updated transfer status to success, transfer code: {transfer_code}")
            else:
                webhook_logger.info(f"Transfer already verified, transfer code: {transfer_code}")
    except Exception as e:
         webhook_logger.error(f"An error occured in transfer.success webhook handler, error is: {e}, for transfer code: {transfer_code}")

def handle_failed_transfer(payload):
    '''
        This function is used to handle failed transfers
    '''
    transfer_code = payload['data']['transfer_code']
    status = payload['data']['status']
    reason = payload['data']['reason']
    try:
        try:
            paystack_transaction = Transaction.objects.get(paystack_transfer_code=transfer_code)
        except Transaction.DoesNotExist:
             webhook_logger.error(f"Transaction record not found for transfer code: {transfer_code}")
             return
         # If not successful, update the status
        with transaction.atomic():
            if paystack_transaction.status != status:
                  paystack_transaction.status = status
                  paystack_transaction.save()
                  # Update Vendor Balance
                  if paystack_transaction.vendor:
                       vendor = paystack_transaction.vendor
                       vendor.wallet_balance += paystack_transaction.amount
                       vendor.save()
                       webhook_logger.info(f"Failed transfer for vendor: {vendor.name}, amount {paystack_transaction.amount} was returned, Reason for failiure is {reason}, transfer code is : {transfer_code}")
            else:
                webhook_logger.info(f"Transaction with reference {reference} is already {status}")
    except Exception as e:
           webhook_logger.error(f"An error occured in transfer.failed webhook handler, error is: {e}, for transfer code: {transfer_code}")


def handle_reversed_transfer(payload):
    '''
        This function is used to handle reversed paystack transfers.
    '''
    transfer_code = payload['data']['transfer_code']
    status = payload['data']['status']
    reason = payload['data']['reason']
    amount = payload['data']['amount']
    try:
         try:
            paystack_transaction = Transaction.objects.get(paystack_transfer_code=transfer_code)
         except Transaction.DoesNotExist:
             webhook_logger.error(f"Transaction record not found for transfer code: {transfer_code}")
             return
        
        # Update the transaction status and balance
         with transaction.atomic():
            if paystack_transaction.status != status:
                  paystack_transaction.status = status
                  paystack_transaction.save()
                   # Update Vendor Balance
                  if paystack_transaction.vendor:
                       vendor = paystack_transaction.vendor
                       vendor.wallet_balance += Decimal(amount) / 100
                       vendor.save()
                       webhook_logger.info(f"Reversed transfer for vendor: {vendor.name}, amount {amount} was returned, Reason for failiure is {reason}, transfer code is : {transfer_code}")
            else:
                webhook_logger.info(f"Transaction with reference {transfer_code} is already {status}")
    except Exception as e:
            webhook_logger.error(f"An error occured in transfer.reversed webhook handler, error is: {e}, for transfer code: {transfer_code}")