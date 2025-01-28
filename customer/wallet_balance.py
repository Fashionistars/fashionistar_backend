from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from userauths.models import User, Profile
from Paystack_Webhoook_Prod.models import  Transaction
from decimal import Decimal
from django.db import transaction
import logging

# Get logger for application
application_logger = logging.getLogger('application')




class UserWalletBalanceView(APIView):
    """
     API endpoint for retrieving the wallet balance of the current authenticated user.

        *   **URL:** `/api/users/wallet-balance/`
        *   **Method:** `GET`
        *   **Authentication:** Requires a valid authentication token in the `Authorization` header.
        *   **Request Body:** None
        *   **Response (JSON):**
                *   On success (HTTP 200 OK):
                    ```json
                    {
                        "balance": 120.00 // The current wallet balance
                    }
                    ```
                *   On failure (HTTP 404):
                        ```json
                            {
                                "error": "Profile not found" // Message if the profile could not be found.
                            }
                        ```
    """
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        user = request.user
        try:
            profile = Profile.objects.get(user=user)
        except Profile.DoesNotExist:
             application_logger.error(f"Profile does not exist for user: {user.email}")
             return Response({'error': 'Profile not found'}, status=status.HTTP_404_NOT_FOUND)

        application_logger.info(f"Successfully retrieved balance for user: {user.email}")
        return Response({'balance': profile.wallet_balance}, status=status.HTTP_200_OK)





class UserTransferView(APIView):
    """
        API endpoint for users to transfer funds to another user.

        *   **URL:** `/api/users/transfer/`
        *   **Method:** `POST`
        *   **Authentication:** Requires a valid authentication token in the `Authorization` header.
        *   **Request Body (JSON):**
                ```json
                {
                    "receiver_id": "uuid", // The UUID of the receiver user
                    "amount": 20, // The amount to transfer (positive decimal)
                    "transaction_password": "1234" // Sender's transaction password
                }
                ```
                *   `receiver_id`: (string, required) The UUID of the user who is receiving the money
                *   `amount`: (decimal, required) The amount of money the sender wants to send to the receiver. Must be a positive value
                *   `transaction_password`: (string, required) The transaction password for the sender.
        *   **Response (JSON):**
                *   On success (HTTP 200 OK):
                    ```json
                    {
                    "message": "Transfer successful", // Success message
                    "sender_balance": 120.00, // The sender's new balance after transfer
                    "receiver_balance": 220.00  // The receiver's new balance after transfer
                    }
                    ```
                *    On failure (HTTP 400 or 404):
                    ```json
                   {
                       "error": "Error message" // Error message explaining the failure
                   }
                    ```
                Possible error messages:
                 *    `"Receiver ID is required"`: if the `receiver_id` is not present in the request body.
                *   `"Amount is required"`: if the amount is not present in the request body.
                *    `"Transaction password is required"`: if the transaction password is not present in the request body.
                *    `"Amount must be positive"`: If amount is not a positive number.
                *    `"Invalid amount format"`: If the amount entered is not a number.
                *   `"Sender profile not found"`: if the sender's profile was not found.
                *   `"Invalid transaction password"`: if the transaction password entered is incorrect.
                *    `"Insufficient balance"`: If the sender does not have enough funds for the transfer.
                *    `"Receiver user not found"`: if the receiver was not found using the `receiver_id` provided
                 *    `"Receiver profile not found"`: if the receiver's profile was not found.
    """
    permission_classes = (IsAuthenticated,)

    def post(self, request):
        sender = request.user
        receiver_id = request.data.get('receiver_id')
        amount = request.data.get('amount')
        transaction_password = request.data.get('transaction_password')
        
        if not receiver_id:
             application_logger.error(f"Receiver ID is required for transfer from user: {sender.email}")
             return Response({'error': 'Receiver ID is required'}, status=status.HTTP_400_BAD_REQUEST)

        if not amount:
              application_logger.error(f"Amount is required for transfer from user: {sender.email}")
              return Response({'error': 'Amount is required'}, status=status.HTTP_400_BAD_REQUEST)

        if not transaction_password:
              application_logger.error(f"Transaction password is required for transfer from user: {sender.email}")
              return Response({'error': 'Transaction password is required'}, status=status.HTTP_400_BAD_REQUEST)
        try:
             amount = Decimal(amount)
             if amount <= 0:
                  application_logger.error(f"Amount must be a positive number for transfer for user: {sender.email}, amount is {amount}")
                  return Response({'error': 'Amount must be positive'}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
             application_logger.error(f"Invalid amount format for transfer from user: {sender.email}: {e}")
             return Response({'error': 'Invalid amount format'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            sender_profile = Profile.objects.get(user=sender)
        except Profile.DoesNotExist:
             application_logger.error(f"Profile does not exist for sender {sender.email}")
             return Response({'error': 'Sender profile not found'}, status=status.HTTP_404_NOT_FOUND)

        if not sender_profile.check_transaction_password(transaction_password):
            application_logger.error(f"Invalid transaction password entered for transfer for user {sender.email}")
            return Response({'error': 'Invalid transaction password'}, status=status.HTTP_400_BAD_REQUEST)

        if sender_profile.wallet_balance < amount:
             application_logger.error(f"Insufficient balance for transfer for user {sender.email}")
             return Response({'error': 'Insufficient balance'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            receiver = User.objects.get(id=receiver_id)
        except User.DoesNotExist:
             application_logger.error(f"Receiver user with id: {receiver_id} not found")
             return Response({'error': 'Receiver user not found'}, status=status.HTTP_404_NOT_FOUND)

        try:
             receiver_profile = Profile.objects.get(user=receiver)
        except Profile.DoesNotExist:
             application_logger.error(f"Profile does not exist for receiver with user id: {receiver_id}")
             return Response({'error': 'Receiver profile not found'}, status=status.HTTP_404_NOT_FOUND)

        with transaction.atomic():
            # Create debit transaction for sender
            Transaction.objects.create(
                user=sender,
                transaction_type='debit',
                amount=amount,
                status='success',
            )

            # Create credit transaction for receiver
            Transaction.objects.create(
                user=receiver,
                transaction_type='credit',
                amount=amount,
                status='success',
            )

            # Update balances
            sender_profile.wallet_balance -= amount
            sender_profile.save()
            receiver_profile.wallet_balance += amount
            receiver_profile.save()
            application_logger.info(f"Successfully transferred {amount} from user: {sender.email} to user: {receiver.email}")

        return Response({'message': 'Transfer successful',
         'sender_balance': sender_profile.wallet_balance,
         'receiver_balance': receiver_profile.wallet_balance
         }, status=status.HTTP_200_OK)
