from django.shortcuts import render
from rest_framework import serializers
import os
from rave_python import Rave
from rest_framework.decorators import api_view
from rest_framework.response import Response
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


class InitiatePayment(APIView):

    permission_classes = [IsAuthenticated]

    def post(self, request):
        total_amount = request.data.get('total_amount')  # Change to POST for form data(if you are using templates) or request.data.get for JSON
        email = request.data.get('email')
        reference = str(uuid.uuid4())

        user = request.user

        if user.is_anonymous:
            return Response({'error': 'User is not authenticated'}, status=400)

        # Replace these with your actual Flutterwave details
        flutterwave_url = "https://api.flutterwave.com/v3/payments"
        secret_key = "FLUTTERWAVE_SECRET_KEY"  #"your_flutterwave_secret_key_here"

        payload = {
            "tx_ref": reference,
            "amount": total_amount,
            "currency": "NGN",
            "redirect_url": "http://127.0.0.1:8000/payment/callback",#(Note this url must be hosted)  # Replace with your callback URL
            "payment_type": "card",
            "customer": {
                "email": email
                }
            }

        headers = {
            "Authorization": f"Bearer {settings.SECRET_KEY}",
            "Content-Type": "application/json"
        }

        try:
            payment = Payment(user=user, amount=total_amount, reference=reference, status="pending")
            payment.save()

            response = requests.post(flutterwave_url, json=payload, headers=headers)
            response_data = response.json()
            return Response(response_data, status=status.HTTP_200_OK)

        except requests.exceptions.RequestException as err:
            # Handle request exceptions
            return Response({'error': 'Payment initiation failed'}, status=500)
        except ValueError as err:
            # Handle JSON decoding error
            return Response({'error': 'Payment initiation failed'}, status=500)

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
