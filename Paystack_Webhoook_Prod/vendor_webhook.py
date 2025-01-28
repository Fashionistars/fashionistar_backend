from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.conf import settings
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from vendor.models import Vendor
from decimal import Decimal
import json
import hashlib
import hmac
from django.db import transaction
import logging

# Get logger for webhook
webhook_logger = logging.getLogger('webhook')
# Get logger for paystack
paystack_logger = logging.getLogger('paystack')

@csrf_exempt
def paystack_transfer_webhook_view(request):
    '''
    This function handles transfer webhook requests from paystack
    '''
    if request.method == 'POST':
        # Get Paystack Signature
        paystack_signature = request.headers.get('X-Paystack-Signature')
        # Get webhook payload
        payload = request.body.decode('utf-8')

        if not paystack_signature:
            webhook_logger.error("Paystack signature is missing from transfer webhook header.")
            return HttpResponse(status=400)

        # Verify if request is from paystack
        if not verify_paystack_signature(payload, paystack_signature, settings.PAYSTACK_SECRET_KEY):
           webhook_logger.error(f"Invalid paystack signature received in transfer webhook : {paystack_signature}")
           return HttpResponse(status=401)

        # Parse Payload
        try:
             payload_data = json.loads(payload)
        except json.JSONDecodeError:
             webhook_logger.error(f"Error decoding json payload from paystack transfer webhook: {payload}")
             return HttpResponse(status=400)

        #Handle event
        handle_paystack_transfer_event(payload_data)

        return HttpResponse(status=200)
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
             paystack_logger.warning("Paystack signature verification failed during transfer webhook.")
             return False
    except Exception as e:
        paystack_logger.error(f"Error while verifying paystack signature during transfer webhook: {e}")
        return False

def handle_paystack_transfer_event(payload):
      '''
      This function handles all paystack transfer event.
      '''
      event = payload.get('event')
      if event == 'transfer.success':
        handle_successful_transfer(payload)
      elif event == 'transfer.failed':
        handle_failed_transfer(payload)
      else:
         webhook_logger.warning(f"Unhandled transfer webhook event: {event}, payload is {payload}")

def handle_successful_transfer(payload):
     '''
     This function handles paystack successful transfer event.
     '''
     reference = payload['data']['reference']
     try:
         paystack_transaction = Transaction.objects.get(paystack_payment_reference=reference)
     except Transaction.DoesNotExist:
        webhook_logger.error(f"Transaction record not found for reference {reference} in transfer webhook")
        return

     with transaction.atomic():
        # Update transaction status if not already success
         if paystack_transaction.status != 'success':
             paystack_transaction.status = 'success'
             paystack_transaction.save()
             webhook_logger.info(f"Successfully updated the status of transaction with reference: {reference} in transfer webhook")
         else:
           webhook_logger.info(f"Transaction with reference {reference} is already successful")

def handle_failed_transfer(payload):
     '''
        This function is used to handle failed paystack transfers.
     '''
     reference = payload['data']['reference']
     status = payload['data']['status']
     reason = payload['data']['reason']
     try:
          paystack_transaction = Transaction.objects.get(paystack_payment_reference=reference)
     except Transaction.DoesNotExist:
        webhook_logger.error(f"Transaction record not found for reference: {reference} in transfer webhook")
        return
     # Update the transaction status and balance
     with transaction.atomic():
       if paystack_transaction.status != status:
           paystack_transaction.status = status
           paystack_transaction.save()
            # Update Vendor Balance
           if paystack_transaction.vendor:
               vendor = paystack_transaction.vendor
               vendor.balance += paystack_transaction.amount
               vendor.save()
               webhook_logger.info(f"Failed transfer for vendor: {vendor.name}, amount {paystack_transaction.amount} was returned, Reason for failiure is {reason}")
       else:
            webhook_logger.info(f"Transaction with reference {reference} is already {status}")