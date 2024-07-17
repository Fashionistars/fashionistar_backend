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
        currency = request.data.get('currency')
        email = request.data.get('email')
        phone_number = request.data.get('phonenumber')
        first_name = request.data.get('firstname')
        last_name = request.data.get("lastname")
        ip = request.data.get("ip")
        reference = str(uuid.uuid4())

        user = request.user

        if user.is_anonymous:
            return Response({'error': 'User is not authenticated'}, status=400)

        flutterwave_url = "https://api.flutterwave.com/v3/payments"
        payload = {
            "cardno": card_number,
            "cvv": cvv,
            "expirymonth": expiry_month,
            "expiryyear": expiry_year,
            "amount": amount,
            "currency": currency,
            "email": email,
            "phonenumber": phone_number,
            "firstname": first_name,
            "lastname": last_name,
            "IP": ip,
            "redirect_url": 'https://example_company.com/success',
            # "authorization": {
            # "mode": "redirect",
        #     "city":  "San Francisco",
        #     "address":  "69 Fremont Street",
        #     "state":  "CA",
        #     "country":  "US",
        #     "zipcode":  "94105"
        #   }
            "authorization": {
        "mode": "pin",
        "pin": "3310"
    }

            }
        headers = {
            "Authorization": "Bearer FLWSECK_TEST-7ec46444d9ede5c450740457bf804f77-X",
            "Content-Type": "application/json"
        }
        rave = Rave(secretKey="FLWSECK_TEST-7ec46444d9ede5c450740457bf804f77-X", publicKey="FLWPUBK_TEST-3001e7f2f30b9a015ac6c1ff857c913c-X", usingEnv=False,production=False)

        try:
            res = rave.Card.charge(payload)
            print(res)
            if res["suggestedAuth"]:
                arg = Misc.getTypeOfArgsRequired(res["suggestedAuth"])

                if arg == "pin":
                    Misc.updatePayload(res["suggestedAuth"], payload, pin="3310")
                if arg == "address":
                    Misc.updatePayload(res["suggestedAuth"], payload, address= {"billingzip": "07205", "billingcity": "Hillside", "billingaddress": "470 Mundet PI", "billingstate": "NJ", "billingcountry": "US"})
                
                res = rave.Card.charge(payload)

            if res["validationRequired"]:
                new_res = rave.Card.validate(res["flwRef"], "")

            res = rave.Card.verify(res["txRef"])
            # print(res)
            # print("Print verify",res["transactionComplete"])
            return Response(res, status=status.HTTP_201_CREATED)

        except RaveExceptions.CardChargeError as e:
            print("Hmmmm",e.err["errMsg"])
            print("Lolalo",e.err["flwRef"])
            return Response(f"This {e.err}", status=status.HTTP_402_PAYMENT_REQUIRED)

        except RaveExceptions.TransactionValidationError as e:
            print("Possibly this",e.err)
            print("Or this could be",e.err["flwRef"])
            return Response(f"Or that? {e.err}", status=status.HTTP_401_UNAUTHORIZED)

        except RaveExceptions.TransactionVerificationError as e:
            print("Could it be this?",e.err["errMsg"])
            print("Or maybe it Could it be this?",e.err["txRef"])
            return Response(f"Maybe {e.err}", status=status.HTTP_400_BAD_REQUEST)