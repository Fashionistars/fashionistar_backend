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
    '''
    This function handles webhook requests from paystack
    '''
    if request.method == 'POST':
        # Get Paystack Signature
        paystack_signature = request.headers.get('X-Paystack-Signature')
        # Get webhook payload
        payload = request.body.decode('utf-8')

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
        except json.JSONDecodeError:
             webhook_logger.error(f"Error decoding json payload from paystack webhook: {payload}")
             return HttpResponse(status=400)

        #Handle event
        handle_paystack_event(payload_data)

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
             paystack_logger.warning("Paystack signature verification failed.")
             return False
    except Exception as e:
        paystack_logger.error(f"Error while verifying paystack signature: {e}")
        return False

def handle_paystack_event(payload):
    '''
    This function handles all paystack event
    '''
    event = payload.get('event')
    if event == 'charge.success':
      handle_successful_charge(payload)
    elif event == 'charge.failed':
      handle_failed_charge(payload)
    else:
       webhook_logger.warning(f"Unhandled webhook event: {event}, payload is {payload}")


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

     with transaction.atomic():
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
              print('Payment already verified.')


def handle_failed_charge(payload):
      '''
        This function is used to handle failed payments
      '''
      reference = payload['data']['reference']
      status = payload['data']['status']
      try:
            paystack_transaction = Transaction.objects.get(paystack_payment_reference=reference)
      except Transaction.DoesNotExist:
          webhook_logger.error(f"Transaction record does not exist for reference: {reference}")
          return
      # If not successful, update the status
      if paystack_transaction.status != status:
            paystack_transaction.status = status
            paystack_transaction.save()
            webhook_logger.info(f"Updated transaction status to: {status}, reference {reference}")
      else:
           webhook_logger.info(f"Status is already updated to: {status}, reference {reference}")
           print("Status is already updated")