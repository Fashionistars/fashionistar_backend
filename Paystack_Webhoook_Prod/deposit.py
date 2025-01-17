from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated, AllowAny
from django.conf import settings
from userauths.models import User, Profile
from Paystack_Webhoook_Prod.paystack import Transaction as PaystackTransaction, verify_payment
from decimal import Decimal
from django.db import transaction
from Paystack_Webhoook_Prod.models import Transaction
import logging

# Get logger for application
application_logger = logging.getLogger('application')


class UserDepositView(APIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request):
        user = request.user
        email = user.email # Use the users email
        amount = request.data.get('amount')

        if not amount:
            application_logger.error(f"Amount is required to make deposit for user {user.email}")
            return Response({'error': 'Amount is required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
             amount = Decimal(amount)
             if amount <= 0:
                 application_logger.error(f"Amount must be a positive number for user {user.email}, amount was {amount}")
                 return Response({'error': 'Amount must be positive'}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
             application_logger.error(f"Invalid amount format for user {user.email}: {e}")
             return Response({'error': 'Invalid amount format'}, status=status.HTTP_400_BAD_REQUEST)
       
        # Initialize Paystack transaction
        paystack_transaction = PaystackTransaction(email, amount)       #, callback_url="https://yourdomain.com/api/users/deposit/verify/")  # Add the callback url TO PAYSTACK DASHBOARD
        paystack_response = paystack_transaction.initialize_transaction()

        if not paystack_response.get("status"):
            application_logger.error(f"Failed to initialize transaction with paystack for user {user.email}, paystack response was: {paystack_response}")
            return Response(
                {"error": "Failed to initialize transaction with paystack", 'paystack_response': paystack_response},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Create pending transaction record in our system
        Transaction.objects.create(
            user=user,
            transaction_type="credit",
            amount=amount,
            paystack_payment_reference=paystack_response['data']['reference'],
            status="pending"
        )
        application_logger.info(f"Payment initialized for user {user.email}, transaction ref is: {paystack_response['data']['reference']}")

        return Response(
            {'message': 'Payment initialized',
             'paystack_response': paystack_response,
             'reference': paystack_response['data']['reference']},
            status=status.HTTP_200_OK
        )


class UserVerifyDepositView(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request, reference):
      try:
        transaction = Transaction.objects.get(paystack_payment_reference=reference)
      except Transaction.DoesNotExist:
            application_logger.error(f"Transaction record does not exist for reference {reference}, user email is: {request.user.email}")
            return Response({"error": "Invalid transaction or reference"}, status=status.HTTP_404_NOT_FOUND)
      
      application_logger.info(f"Payment verification successful for user {request.user.email}, transaction status is {transaction.status}")
      return Response({
        'message': 'Payment verification successful',
        'transaction_status': transaction.status,
         'new_balance': Profile.objects.get(user=request.user).wallet_balance,
         }, status=status.HTTP_200_OK)