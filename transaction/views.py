from django.shortcuts import render
from rest_framework import serializers
import os
from rave_python import Rave
from rest_framework.decorators import api_view
from rest_framework.response import Response

from ShopCart.models import Cart
from .serializers import PaymentSerializer
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

import requests
from rest_framework.permissions import IsAuthenticated
import uuid
from transaction.models import Payment
from django.conf import settings

from store.models import *

from environs import Env
import os
import logging
from django.conf import settings
from rave_python import Rave, RaveExceptions, Misc

# Initialize logger
logger = logging.getLogger(__name__)

from rave_python import Rave

env = Env()
env.read_env()

rave = Rave(publicKey="", usingEnv=False)


class PaymentCallback(APIView):
    def get(self, request):
        status = request.GET.get('status')
        tx_ref = request.GET.get('tx_ref')

        if status == 'successful':
            try:
                payment = Payment.objects.get(reference=tx_ref)
                payment.status = "successful"
                payment.save()

                cart_items = Cart.objects.filter(user=payment.user, payment__isnull=True)
                payment.items.set(cart_items.values_list('items', flat=True))

                # Create an order with payment information
                # order = Order.objects.create(
                #     user=payment.user,
                #     total_cost=payment.amount,
                #     payment=payment
                # )

                # Add the items related to the payment to the order
                # order.items.set(cart_items.values_list('items', flat=True))
                cart_items.update(payment=payment)

                return Response({'message': 'Payment was successful'})

            except Payment.DoesNotExist:
                return Response({'error': 'Payment not found'}, status=status.HTTP_404_NOT_FOUND)

        return Response({'error': 'Payment failed'})



class InitiateNewPayment(APIView):
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        card_number = request.data.get("card_number")
        cvv = request.data.get('cvv')
        expiry_month = request.data.get('expiry_month')
        expiry_year = request.data.get("expiry_year")
        amount = request.data.get('amount')
        email = request.data.get('email')
        reference = str(uuid.uuid4())

        user = request.user

        if user.is_anonymous:
            return Response({'error': 'User is not authenticated'}, status=400)

        # Replace these with your actual Flutterwave details
        flutterwave_url = "https://api.flutterwave.com/v3/payments"
        secret_key = ""  #"your_flutterwave_secret_key_here"

        payload = {
            "tx_ref": reference,
            "amount": amount,
            "currency": "NGN",
            "cardno": card_number,
            "cvv": cvv,
            "expirymonth": expiry_month,
            "expiryyear": expiry_year,
            "redirect_url": "http://127.0.0.1:8000/payment/callback",#(Note this url must be hosted)  # Replace with your callback URL
            "payment_type": "card",
            "email": email,
            "authorization": {
                "mode": "pin", 
                "pin": "3310"
                }
            }

        headers = {
            "Authorization": f"Bearer {settings.SECRET_KEY}",
            "Content-Type": "application/json"
        }

        try:
            payment = Payment(user=user, total_amount=amount, reference=reference, status="pending")
            payment.save()
            
            logger.debug("Payload: %s", payload)
            logger.debug("Headers: %s", headers)
            
            rave = Rave( publicKey="", usingEnv=False,production=False)
            
            response = rave.Card.charge(payload)
            logger.debug("Response: %s", response)
            
            # Handle response and update payment status accordingly
            if response["error"]:
                payment.status = "failed"
                payment.save()
                logger.error("Payment failed: %s", response)
                return Response({"error": "Payment failed"}, status=400)

            payment.status = "successful"
            payment.save()
            return Response({"success": "Payment successful"}, status=200)

        except RaveExceptions.CardChargeError as e:
            logger.exception("Card charge error: %s", e)
            return Response({"error": f"Card charge error {e}"}, status=500)
        except Exception as e:
            logger.exception("An error occurred: %s", e)
            return Response({"error": f"An error occurred {e}"}, status=500)


