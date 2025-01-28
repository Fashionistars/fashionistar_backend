from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated, AllowAny
from django.conf import settings
from userauths.models import User, Profile
from Paystack_Webhoook_Prod.UTILS.paystack import Transaction as PaystackTransaction, verify_payment
from decimal import Decimal
from django.db import transaction
from Paystack_Webhoook_Prod.models import Transaction

from Paystack_Webhoook_Prod.serializers import DepositAmountSerializer  # Import the serializer you just created

import logging

# Get logger for application
application_logger = logging.getLogger('application')


class UserDepositView(APIView):
    permission_classes = (IsAuthenticated,)
    serializer_class = DepositAmountSerializer
    
    def post(self, request, *args, **kwargs):
        """
        Initiates a deposit request by a logged-in user and processes the payment with Paystack.

        Steps:
        1. The user makes a POST request with the amount they wish to deposit.
        2. The `amount` is validated to ensure it is a positive number.
        3. The Paystack transaction is initialized using the user's email and deposit amount.
        4. A Paystack transaction is created and stored in the local database with a 'pending' status.
        5. If Paystack initialization is successful, the transaction reference is returned to the user.
        6. If any validation or transaction fails, appropriate error responses are provided.

        Frontend considerations:
        - The frontend should ensure that only the `amount` field is sent in the request body.
        - The response will include a `message`, Paystack's `paystack_response`, and the `reference` for the user.
        - Any errors encountered will be returned as JSON, with the error message and status code.

        Payload Example:
        {
            "amount": 100.50
        }

        Returns:
        - 200 OK with transaction details if successful.
        - 400 Bad Request with error details if any validation fails or Paystack transaction fails.
        """
        try:
            user = request.user
            email = user.email  # Use the user's email for Paystack transaction

            # Deserialize and validate the amount field
            serializer = DepositAmountSerializer(data=request.data)
            if not serializer.is_valid():
                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

            amount = serializer.validated_data['amount']

            # Validate that amount is positive
            if amount <= 0:
                application_logger.error(f"Amount must be a positive number for user {user.email}, amount was {amount}")
                return Response({'error': 'Amount must be positive'}, status=status.HTTP_400_BAD_REQUEST)

            # Initialize Paystack transaction
            paystack_transaction = PaystackTransaction(email, amount)
            paystack_response = paystack_transaction.initialize_transaction()

            if not paystack_response.get("status"):
                application_logger.error(f"Failed to initialize transaction with Paystack for user {user.email}, paystack response was: {paystack_response}")
                return Response(
                    {"error": "Failed to initialize transaction with Paystack", 'paystack_response': paystack_response},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Create a pending transaction record in our system
            Transaction.objects.create(
                user=user,
                transaction_type="credit",
                amount=amount,
                paystack_payment_reference=paystack_response['data']['reference'],
                status="pending"
            )
            application_logger.info(f"Payment initialized for user {user.email}, transaction ref is: {paystack_response['data']['reference']}")

            # Return success response with Paystack details
            return Response(
                {'message': 'Payment initialized',
                 'paystack_response': paystack_response,
                 'reference': paystack_response['data']['reference']},
                status=status.HTTP_200_OK
            )
        except Exception as e:
            application_logger.error(f"Error during deposit transaction for user {request.user.email}: {str(e)}")
            return Response({'error': 'An error occurred while processing the deposit'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)








class UserVerifyDepositView(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request, reference):
        """
        Verifies the payment transaction using Paystack reference.

        Steps:
        1. The user provides the Paystack reference they received during the deposit process.
        2. The system checks the transaction status in the local database using the provided reference.
        3. If the transaction exists, the status of the transaction is returned to the user.
        4. The user's updated wallet balance is also included in the response.
        5. If the reference is invalid or the transaction does not exist, an error is returned.

        Frontend considerations:
        - The frontend should ensure that the reference is passed correctly in the GET request.
        - The response will include a `message`, the transaction `status`, and the updated `new_balance` of the user.
        - Any errors encountered will be returned as JSON with the error message and status code.

        Payload Example:
        {
            "reference": "paystack_reference_string"
        }

        Returns:
        - 200 OK with transaction status and updated balance if successful.
        - 404 Not Found if the reference is invalid or transaction is not found.
        """
        try:
            # Fetch the transaction using the Paystack reference
            transaction = Transaction.objects.get(paystack_payment_reference=reference)

            application_logger.info(f"Payment verification successful for user {request.user.email}, transaction status is {transaction.status}")

            # Return the verification result and user balance
            return Response({
                'message': 'Payment verification successful',
                'transaction_status': transaction.status,
                'new_balance': Profile.objects.get(user=request.user).wallet_balance,
            }, status=status.HTTP_200_OK)

        except Transaction.DoesNotExist:
            application_logger.error(f"Transaction record does not exist for reference {reference}, user email is: {request.user.email}")
            return Response({"error": "Invalid transaction or reference"}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            application_logger.error(f"Error during payment verification for user {request.user.email}: {str(e)}")
            return Response({"error": "An error occurred during verification"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
