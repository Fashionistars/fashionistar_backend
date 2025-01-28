
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from vendor.models import Vendor
from decimal import Decimal
from django.db import transaction
import logging


from userauths.models import User, Profile

from Paystack_Webhoook_Prod.management.commands.Command_for_fetch_banks import fetch_paystack_banks
from Paystack_Webhoook_Prod.UTILS.paystack import Transaction as PaystackTransaction
from Paystack_Webhoook_Prod.models import Transaction


from Paystack_Webhoook_Prod.UTILS.paystack import Transfer as PaystackTransfer, TransferRecipient as PaystackTransferRecipient


from django.conf import settings
import json
import os


# Get logger for application
application_logger = logging.getLogger('application')

# class VendorWithdrawView(APIView):
#     """
#     API endpoint for vendors to initiate a withdrawal from their wallet.

#     *   **URL:** `/api/vendor/withdraw/`
#     *   **Method:** `POST`
#     *   **Authentication:** Requires a valid authentication token in the `Authorization` header.
#     *   **Request Body (JSON):**
#         ```json
#        {
#            "amount": 50, // The amount to withdraw (positive decimal)
#            "transaction_password": "1234", // Vendor's transaction password for security
#            "account_number": "0123456789",   // The account number
#            "account_full_name": "John Doe", // Name of the account holder
#            "phone_number":"07012345678",  //Phone number for bank transfer purposes
#            "bank_name":"Access Bank"    // The bank name of the vendor
#         }
#         ```
#         *   `amount`: (Decimal, required) The amount the vendor wants to withdraw from their wallet. Must be a positive value.
#         *   `transaction_password`: (string, required) The transaction password for the vendor.
#         *   `account_number`: (string, required) The vendors bank account number
#         *   `account_full_name` (string, required): The vendors full name registered with the bank
#         *  `phone_number` (string, required): The vendors phone number to receive notifications.
#         *  `bank_name` (string, required): The vendors bank name
#     *   **Response (JSON):**
#          *   On success (HTTP 200 OK):
#                 ```json
#               {
#                 "message": "Withdrawal initiated", // Success message
#                 "new_balance": 120.00 // The vendor's new balance after withdrawal
#               }
#              ```
#          *   On failure (HTTP 400, 404 or 302):
#                 ```json
#                 {
#                     "error": "Error message" // Error message explaining the failure
#                 }
#                ```
#                 Possible error messages:
#                 *   `"Amount is required"`: if the amount is not present in the request body.
#                  *    `"Transaction password is required"`: if the transaction password is not present in the request body
#                 *    `"Amount must be positive"`: If amount is not a positive number.
#                 *    `"Invalid amount format"`: If the amount entered is not a number.
#                 *   `"Profile not found"`: If the vendor's profile is not found.
#                  *   `"Vendor not found"`: If the vendor is not found
#                  *   `"Transaction password not set. Please set it first."`: If the transaction password has not been set for the vendor.
#                 *   `"Invalid transaction password"`: If an incorrect transaction password was provided.
#                 *  `"Insufficient balance"`: If the vendor's balance is lower than the withdrawal amount.
#                  *  `"account_number is required"`: If the account number was not provided
#                  *  `"account_full_name is required"`: If the account full name was not provided
#                  *  `"phone_number is required"`: if the phone number was not provided
#                  *  `"bank_name is required"`: If the bank name was not provided
#                  * ` "error": "Failed to transfer funds"`: if the transfer process with paystack failed.
#                  *   `"redirect_url": "/set-transaction-password/"` The url where the vendor is directed to set up their password for the first time.
#     """
#     permission_classes = (AllowAny,)

#     def post(self, request):
#         user = request.user
#         amount = request.data.get('amount')
#         transaction_password = request.data.get('transaction_password')
#         account_number = request.data.get('account_number')
#         account_full_name = request.data.get('account_full_name')
#         phone_number = request.data.get('phone_number')
#         bank_name = request.data.get('bank_name')
#         if not amount:
#              application_logger.error(f"Amount is required for withdrawal for vendor: {user.email}")
#              return Response({'error': 'Amount is required'}, status=status.HTTP_400_BAD_REQUEST)
#         if not transaction_password:
#              application_logger.error(f"Transaction password is required for withdrawal for vendor: {user.email}")
#              return Response({'error': 'Transaction password is required'}, status=status.HTTP_400_BAD_REQUEST)
#         if not account_number:
#              application_logger.error(f"account_number is required for withdrawal for vendor: {user.email}")
#              return Response({'error': 'account_number is required'}, status=status.HTTP_400_BAD_REQUEST)
#         if not account_full_name:
#              application_logger.error(f"account_full_name is required for withdrawal for vendor: {user.email}")
#              return Response({'error': 'account_full_name is required'}, status=status.HTTP_400_BAD_REQUEST)
#         if not phone_number:
#              application_logger.error(f"phone_number is required for withdrawal for vendor: {user.email}")
#              return Response({'error': 'phone_number is required'}, status=status.HTTP_400_BAD_REQUEST)
#         if not bank_name:
#              application_logger.error(f"bank_name is required for withdrawal for vendor: {user.email}")
#              return Response({'error': 'bank_name is required'}, status=status.HTTP_400_BAD_REQUEST)
#         try:
#              amount = Decimal(amount)
#              if amount <= 0:
#                   application_logger.error(f"Amount for withdrawal must be positive for vendor: {user.email}, amount was {amount}")
#                   return Response({'error': 'Amount must be positive'}, status=status.HTTP_400_BAD_REQUEST)
#         except Exception as e:
#              application_logger.error(f"Invalid amount format for withdrawal for vendor: {user.email}: {e}")
#              return Response({'error': 'Invalid amount format'}, status=status.HTTP_400_BAD_REQUEST)

#         try:
#              vendor = Vendor.objects.get(user=user)
#         except Vendor.DoesNotExist:
#              application_logger.error(f"Vendor does not exist for user: {user.email}")
#              return Response({'error': 'Vendor not found'}, status=status.HTTP_404_NOT_FOUND)

#         try:
#              profile = Profile.objects.get(user=user)
#         except Profile.DoesNotExist:
#              application_logger.error(f"Profile does not exist for vendor: {user.email}")
#              return Response({'error': 'Profile not found'}, status=status.HTTP_404_NOT_FOUND)
        
#         #validate transaction password
#         if not vendor.transaction_password:
#             # Custom response to prompt setting a transaction password
#             return Response(
#                 {
#                     "message": "Transaction password not set. Please set it first.",
#                     "redirect_url": "/set-transaction-password/"
#                 },
#                 status=status.HTTP_302_FOUND  # Using 302 status code to indicate redirection
#             )


#         if not vendor.check_transaction_password(transaction_password):
#             application_logger.error(f"Invalid transaction password entered for user {user.email}")
#             return Response({'error': 'Invalid transaction password'}, status=status.HTTP_400_BAD_REQUEST)

#         if profile.wallet_balance < amount:
#             application_logger.error(f"Insufficient balance for withdrawal for vendor {user.email}")
#             return Response({'error': 'Insufficient balance'}, status=status.HTTP_400_BAD_REQUEST)

#         try:
#              # fetch bank list from the file
#             project_dir = os.path.dirname(os.path.abspath(__file__))
#             json_path = os.path.join(project_dir, 'banks.json')
#             with open(json_path, 'r') as f:
#                 banks = json.load(f)

#             # find the bank code
#             recipient_bank = next((bank for bank in banks if bank['name'] == bank_name), None)
#             if not recipient_bank:
#                   application_logger.error(f"Invalid bank name: {bank_name}, for user: {user.email}")
#                   return Response({'error': 'Invalid bank name'}, status=status.HTTP_400_BAD_REQUEST)

#             recipient_code = recipient_bank['code']
#             #initialize transfer
#             paystack_transfer = PaystackTransaction(amount=amount, recipient_code=recipient_code, recipient_account_number=account_number, recipient_name=account_full_name, phone_number=phone_number)
#             transfer_response = paystack_transfer.initiate_transfer()
#             if not transfer_response["status"]:
#                  application_logger.error(f"Failed to transfer funds for user: {user.email}, paystack error response: {transfer_response}")
#                  return Response({"error": "Failed to transfer funds"}, status=status.HTTP_400_BAD_REQUEST)
        
#         except Exception as e:
#              application_logger.error(f"Error during paystack transfer initiation for user {user.email}: {e}")
#              return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        
#         with transaction.atomic():
#             # Create a new debit transaction
#             Transaction.objects.create(
#                 vendor=vendor,
#                 transaction_type='debit',
#                 amount=amount,
#                 status='pending',
#                 account_number=account_number,
#                 account_full_name=account_full_name,
#                 phone_number=phone_number,
#                 bank_name=bank_name,
#                 paystack_payment_reference=transfer_response['data']['transfer_code']
#             )

#              # Update vendor Balance
#             profile.wallet_balance -= amount
#             profile.save()
#             application_logger.info(f"Withdrawal of {amount} initiated by vendor: {user.email}, transfer code is: {transfer_response['data']['transfer_code']}")

#         return Response({'message': 'Withdrawal initiated',
#          'new_balance': profile.wallet_balance,
#          'transfer_code':transfer_response['data']['transfer_code'],
#          }, status=status.HTTP_200_OK)









class VendorWalletBalanceView(APIView):
    """
    API endpoint for retrieving the wallet balance of the current authenticated vendor.
        *   **URL:** `/api/vendors/wallet-balance/`
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
                *   On failure (HTTP 400 or 404):
                    ```json
                        {
                             "error": "Error message" // Message if the profile could not be found or the user is not a vendor.
                         }
                   ```
                   Possible Error Messages:
                   * `"Profile not found"`: If profile was not found
                   * `"You are not a vendor"`: If user is not a vendor.
    """
    permission_classes = (IsAuthenticated,)

    def get(self, request):
         user = request.user
         try:
            vendor_profile = Profile.objects.get(user=user)
         except Profile.DoesNotExist:
              application_logger.error(f"Profile does not exist for vendor: {user.email}")
              return Response({'error': 'Profile not found'}, status=status.HTTP_404_NOT_FOUND)
         if user.role != 'vendor':
             application_logger.error(f"User: {user.email} is not a vendor")
             return Response({'error': "You are not a vendor"}, status=status.HTTP_400_BAD_REQUEST)
         application_logger.info(f"Successfully retrieved balance for vendor {user.email}")
         return Response({'balance': vendor_profile.wallet_balance}, status=status.HTTP_200_OK)











# # Get logger for application
# application_logger = logging.getLogger('application')

# class VendorWithdrawView(APIView):
#  """
#  API endpoint for vendors to initiate a withdrawal from their wallet.

#  *   **URL:** `/api/vendor/withdraw/`
#  *   **Method:** `POST`
#  *   **Authentication:** Requires a valid authentication token in the `Authorization` header.
#  *   **Request Body (JSON):**
#      ```json
#     {
#         "amount": 50, // The amount to withdraw (positive decimal)
#         "transaction_password": "1234", // Vendor's transaction password for security
#         "account_number": "0123456789",   // The account number
#         "account_full_name": "John Doe", // Name of the account holder
#         "phone_number":"07012345678",  //Phone number for bank transfer purposes
#         "bank_name":"Access Bank"    // The bank name of the vendor
#      }
#      ```
#      *   `amount`: (Decimal, required) The amount the vendor wants to withdraw from their wallet. Must be a positive value.
#      *   `transaction_password`: (string, required) The transaction password for the vendor.
#      *   `account_number`: (string, required) The vendors bank account number
#      *   `account_full_name` (string, required): The vendors full name registered with the bank
#      *  `phone_number` (string, required): The vendors phone number to receive notifications.
#      *  `bank_name` (string, required): The vendors bank name
#  *   **Response (JSON):**
#       *   On success (HTTP 200 OK):
#              ```json
#            {
#              "message": "Withdrawal initiated", // Success message
#              "new_balance": 120.00 // The vendor's new balance after withdrawal
#              "banks": [("Access Bank", "Access Bank"),("GT Bank", "GT Bank")....]
#            }
#           ```
#       *   On failure (HTTP 400, 404 or 302):
#              ```json
#              {
#                  "error": "Error message" // Error message explaining the failure
#              }
#             ```
#              Possible error messages:
#              *   `"Amount is required"`: if the amount is not present in the request body.
#               *    `"Transaction password is required"`: if the transaction password is not present in the request body
#              *    `"Amount must be positive"`: If amount is not a positive number.
#              *    `"Invalid amount format"`: If the amount entered is not a number.
#              *   `"Profile not found"`: If the vendor's profile is not found.
#               *   `"Vendor not found"`: If the vendor is not found
#               *   `"Transaction password not set. Please set it first."`: If the transaction password has not been set for the vendor.
#              *   `"Invalid transaction password"`: If an incorrect transaction password was provided.
#              *  `"Insufficient balance"`: If the vendor's balance is lower than the withdrawal amount.
#               *  `"account_number is required"`: If the account number was not provided
#               *  `"account_full_name is required"`: If the account full name was not provided
#               *  `"phone_number is required"`: if the phone number was not provided
#               *  `"bank_name is required"`: If the bank name was not provided
#               * ` "error": "Failed to transfer funds"`: if the transfer process with paystack failed.
#               *   `"redirect_url": "/set-transaction-password/"` The url where the vendor is directed to set up their password for the first time.
#  """
#  permission_classes = (IsAuthenticated,)

#  def post(self, request):
#      user = request.user
#      amount = request.data.get('amount')
#      transaction_password = request.data.get('transaction_password')
#      account_number = request.data.get('account_number')
#      account_full_name = request.data.get('account_full_name')
#      phone_number = request.data.get('phone_number')
#      bank_name = request.data.get('bank_name')
#      if not amount:
#           application_logger.error(f"Amount is required for withdrawal for vendor: {user.email}")
#           return Response({'error': 'Amount is required'}, status=status.HTTP_400_BAD_REQUEST)
#      if not transaction_password:
#           application_logger.error(f"Transaction password is required for withdrawal for vendor: {user.email}")
#           return Response({'error': 'Transaction password is required'}, status=status.HTTP_400_BAD_REQUEST)
#      if not account_number:
#           application_logger.error(f"account_number is required for withdrawal for vendor: {user.email}")
#           return Response({'error': 'account_number is required'}, status=status.HTTP_400_BAD_REQUEST)
#      if not account_full_name:
#           application_logger.error(f"account_full_name is required for withdrawal for vendor: {user.email}")
#           return Response({'error': 'account_full_name is required'}, status=status.HTTP_400_BAD_REQUEST)
#      if not phone_number:
#           application_logger.error(f"phone_number is required for withdrawal for vendor: {user.email}")
#           return Response({'error': 'phone_number is required'}, status=status.HTTP_400_BAD_REQUEST)
#      if not bank_name:
#           application_logger.error(f"bank_name is required for withdrawal for vendor: {user.email}")
#           return Response({'error': 'bank_name is required'}, status=status.HTTP_400_BAD_REQUEST)
#      try:
#           amount = Decimal(amount)
#           if amount <= 0:
#                application_logger.error(f"Amount for withdrawal must be positive for vendor: {user.email}, amount was {amount}")
#                return Response({'error': 'Amount must be positive'}, status=status.HTTP_400_BAD_REQUEST)
#      except Exception as e:
#           application_logger.error(f"Invalid amount format for withdrawal for vendor: {user.email}: {e}")
#           return Response({'error': 'Invalid amount format'}, status=status.HTTP_400_BAD_REQUEST)

#      try:
#           vendor = Vendor.objects.get(user=user)
#      except Vendor.DoesNotExist:
#           application_logger.error(f"Vendor does not exist for user: {user.email}")
#           return Response({'error': 'Vendor not found'}, status=status.HTTP_404_NOT_FOUND)

#      try:
#           profile = Profile.objects.get(user=user)
#      except Profile.DoesNotExist:
#           application_logger.error(f"Profile does not exist for vendor: {user.email}")
#           return Response({'error': 'Profile not found'}, status=status.HTTP_404_NOT_FOUND)
     
#      #validate transaction password
#      if not vendor.transaction_password:
#          # Custom response to prompt setting a transaction password
#          return Response(
#              {
#                  "message": "Transaction password not set. Please set it first.",
#                  "redirect_url": "/set-transaction-password/"
#              },
#              status=status.HTTP_302_FOUND  # Using 302 status code to indicate redirection
#          )


#      if not vendor.check_transaction_password(transaction_password):
#          application_logger.error(f"Invalid transaction password entered for user {user.email}")
#          return Response({'error': 'Invalid transaction password'}, status=status.HTTP_400_BAD_REQUEST)

#      if profile.wallet_balance < amount:
#          application_logger.error(f"Insufficient balance for withdrawal for vendor {user.email}")
#          return Response({'error': 'Insufficient balance'}, status=status.HTTP_400_BAD_REQUEST)

#      try:
#           # fetch bank list from the file
#          project_dir = os.path.dirname(os.path.abspath(__file__))
#          json_path = os.path.join(project_dir, 'banks.json')
#          with open(json_path, 'r') as f:
#              banks = json.load(f)

#          # find the bank code
#          recipient_bank = next((bank for bank in banks if bank['name'] == bank_name), None)
#          if not recipient_bank:
#                application_logger.error(f"Invalid bank name: {bank_name}, for user: {user.email}")
#                return Response({'error': 'Invalid bank name'}, status=status.HTTP_400_BAD_REQUEST)

#          recipient_code = recipient_bank['code']
#          #initialize transfer
#          paystack_transfer = PaystackTransaction(amount=amount, recipient_code=recipient_code, recipient_account_number=account_number, recipient_name=account_full_name, phone_number=phone_number)
#          transfer_response = paystack_transfer.initiate_transfer()
#          if not transfer_response["status"]:
#               application_logger.error(f"Failed to transfer funds for user: {user.email}, paystack error response: {transfer_response}")
#               return Response({"error": "Failed to transfer funds"}, status=status.HTTP_400_BAD_REQUEST)
     
#      except Exception as e:
#           application_logger.error(f"Error during paystack transfer initiation for user {user.email}: {e}")
#           return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
     
#      with transaction.atomic():
#          # Create a new debit transaction
#          Transaction.objects.create(
#              vendor=vendor,
#              transaction_type='debit',
#              amount=amount,
#              status='pending',
#              account_number=account_number,
#              account_full_name=account_full_name,
#              phone_number=phone_number,
#              bank_name=bank_name,
#              paystack_payment_reference=transfer_response['data']['transfer_code']
#          )

#           # Update vendor Balance
#          profile.wallet_balance -= amount
#          profile.save()
#          application_logger.info(f"Withdrawal of {amount} initiated by vendor: {user.email}, transfer code is: {transfer_response['data']['transfer_code']}")
#      banks_for_dropdown = get_banks_for_dropdown()

#      return Response({'message': 'Withdrawal initiated',
#       'new_balance': profile.wallet_balance,
#       'transfer_code':transfer_response['data']['transfer_code'],
#        'banks': banks_for_dropdown,
#       }, status=status.HTTP_200_OK)









# Get logger for application
application_logger = logging.getLogger('application')

class VendorWithdrawView(APIView):
  """
  API endpoint for vendors to initiate a withdrawal from their wallet.

  *   **URL:** `/api/vendor/withdraw/`
  *   **Method:** `POST`
  *   **Authentication:** Requires a valid authentication token in the `Authorization` header.
  *   **Request Body (JSON):**
      ```json
     {
         "amount": 50, // The amount to withdraw (positive decimal)
         "transaction_password": "1234", // Vendor's transaction password for security
         "account_number": "0123456789",   // The account number
         "account_full_name": "John Doe", // Name of the account holder
         "phone_number":"07012345678",  //Phone number for bank transfer purposes
         "bank_name":"Access Bank"    // The bank name of the vendor
      }
      ```
      *   `amount`: (Decimal, required) The amount the vendor wants to withdraw from their wallet. Must be a positive value.
      *   `transaction_password`: (string, required) The transaction password for the vendor.
      *   `account_number`: (string, required) The vendors bank account number
      *   `account_full_name` (string, required): The vendors full name registered with the bank
      *  `phone_number` (string, required): The vendors phone number to receive notifications.
      *  `bank_name` (string, required): The vendors bank name
  *   **Response (JSON):**
       *   On success (HTTP 200 OK):
              ```json
            {
              "message": "Withdrawal initiated", // Success message
              "new_balance": 120.00 // The vendor's new balance after withdrawal
              "banks": [("Access Bank", "Access Bank"),("GT Bank", "GT Bank")....]
            }
           ```
       *   On failure (HTTP 400, 404 or 302 or 503):
              ```json
              {
                  "error": "Error message" // Error message explaining the failure
              }
             ```
              Possible error messages:
              *   `"Amount is required"`: if the amount is not present in the request body.
               *    `"Transaction password is required"`: if the transaction password is not present in the request body
              *    `"Amount must be positive"`: If amount is not a positive number.
              *    `"Invalid amount format"`: If the amount entered is not a number.
              *   `"Profile not found"`: If the vendor's profile is not found.
               *   `"Vendor not found"`: If the vendor is not found
               *   `"Transaction password not set. Please set it first."`: If the transaction password has not been set for the vendor.
              *   `"Invalid transaction password"`: If an incorrect transaction password was provided.
              *  `"Insufficient balance"`: If the vendor's balance is lower than the withdrawal amount.
               *  `"account_number is required"`: If the account number was not provided
               *  `"account_full_name is required"`: If the account full name was not provided
               *  `"phone_number is required"`: if the phone number was not provided
               *  `"bank_name is required"`: If the bank name was not provided
               * ` "error": "Failed to transfer funds"`: if the transfer process with paystack failed.
               *  ` "error": "Failed to transfer funds due to paystack server error, please try again later"`: If a 500 error from paystack is returned
               *   `"redirect_url": "/set-transaction-password/"` The url where the vendor is directed to set up their password for the first time.
  """
  permission_classes = (IsAuthenticated,)

  def post(self, request):
      user = request.user
      amount = request.data.get('amount')
      transaction_password = request.data.get('transaction_password')
      account_number = request.data.get('account_number')
      account_full_name = request.data.get('account_full_name')
      phone_number = request.data.get('phone_number')
      bank_name = request.data.get('bank_name')
      if not amount:
           application_logger.error(f"Amount is required for withdrawal for vendor: {user.email}")
           return Response({'error': 'Amount is required'}, status=status.HTTP_400_BAD_REQUEST)
      if not transaction_password:
           application_logger.error(f"Transaction password is required for withdrawal for vendor: {user.email}")
           return Response({'error': 'Transaction password is required'}, status=status.HTTP_400_BAD_REQUEST)
      if not account_number:
           application_logger.error(f"account_number is required for withdrawal for vendor: {user.email}")
           return Response({'error': 'account_number is required'}, status=status.HTTP_400_BAD_REQUEST)
      if not account_full_name:
           application_logger.error(f"account_full_name is required for withdrawal for vendor: {user.email}")
           return Response({'error': 'account_full_name is required'}, status=status.HTTP_400_BAD_REQUEST)
      if not phone_number:
           application_logger.error(f"phone_number is required for withdrawal for vendor: {user.email}")
           return Response({'error': 'phone_number is required'}, status=status.HTTP_400_BAD_REQUEST)
      if not bank_name:
           application_logger.error(f"bank_name is required for withdrawal for vendor: {user.email}")
           return Response({'error': 'bank_name is required'}, status=status.HTTP_400_BAD_REQUEST)
      try:
           amount = Decimal(amount)
           if amount <= 0:
                application_logger.error(f"Amount for withdrawal must be positive for vendor: {user.email}, amount was {amount}")
                return Response({'error': 'Amount must be positive'}, status=status.HTTP_400_BAD_REQUEST)
      except Exception as e:
           application_logger.error(f"Invalid amount format for withdrawal for vendor: {user.email}: {e}")
           return Response({'error': 'Invalid amount format'}, status=status.HTTP_400_BAD_REQUEST)

      try:
           vendor = Vendor.objects.get(user=user)
      except Vendor.DoesNotExist:
           application_logger.error(f"Vendor does not exist for user: {user.email}")
           return Response({'error': 'Vendor not found'}, status=status.HTTP_404_NOT_FOUND)

      try:
           profile = Profile.objects.get(user=user)
      except Profile.DoesNotExist:
           application_logger.error(f"Profile does not exist for vendor: {user.email}")
           return Response({'error': 'Profile not found'}, status=status.HTTP_404_NOT_FOUND)
      
      #validate transaction password
      if not vendor.transaction_password:
          # Custom response to prompt setting a transaction password
          return Response(
              {
                  "message": "Transaction password not set. Please set it first.",
                  "redirect_url": "/set-transaction-password/"
              },
              status=status.HTTP_302_FOUND  # Using 302 status code to indicate redirection
          )


      if not vendor.check_transaction_password(transaction_password):
          application_logger.error(f"Invalid transaction password entered for user {user.email}")
          return Response({'error': 'Invalid transaction password'}, status=status.HTTP_400_BAD_REQUEST)

      if profile.wallet_balance < amount:
          application_logger.error(f"Insufficient balance for withdrawal for vendor {user.email}")
          return Response({'error': 'Insufficient balance'}, status=status.HTTP_400_BAD_REQUEST)

      try:
           # fetch bank list from the file
          project_dir = os.path.dirname(os.path.abspath(__file__))
          json_path = os.path.join(project_dir, 'banks.json')
          with open(json_path, 'r') as f:
              banks = json.load(f)

          # find the bank code
          recipient_bank = next((bank for bank in banks if bank['name'] == bank_name), None)
          if not recipient_bank:
                application_logger.error(f"Invalid bank name: {bank_name}, for user: {user.email}")
                return Response({'error': 'Invalid bank name'}, status=status.HTTP_400_BAD_REQUEST)

          recipient_code = recipient_bank['code']
          # Check if a transfer recipient already exists, if not, then create one
          if not profile.paystack_recipient_code:
             paystack_transfer_recipient = PaystackTransferRecipient(recipient_account_number=account_number, recipient_name=account_full_name, bank_code=recipient_code)
             transfer_recipient_response = paystack_transfer_recipient.create_transfer_recipient()
             if not transfer_recipient_response['status']:
                application_logger.error(f"Failed to create transfer recipient for user: {user.email}, paystack error response: {transfer_recipient_response}")
                return Response({"error":"Failed to create transfer recipient"}, status=status.HTTP_400_BAD_REQUEST)
             profile.paystack_recipient_code = transfer_recipient_response['data']['recipient_code']
             profile.save()
             application_logger.info(f"Transfer recipient created for user: {user.email}, recipient code is {transfer_recipient_response['data']['recipient_code']}")
          else:
            application_logger.info(f"Transfer recipient already exists for user: {user.email}, recipient code is {profile.paystack_recipient_code}")
          
          #initialize transfer
          paystack_transfer = PaystackTransfer(amount=amount, recipient_code=profile.paystack_recipient_code)
          transfer_response = paystack_transfer.initiate_transfer()
          if not transfer_response["status"]:
               application_logger.error(f"Failed to transfer funds for user: {user.email}, paystack error response: {transfer_response}")
               if transfer_response["type"] == "server_error":
                    return Response({"error": "Failed to transfer funds due to paystack server error, please try again later"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
               else:
                    return Response({"error": "Failed to transfer funds"}, status=status.HTTP_400_BAD_REQUEST)
      except Exception as e:
           application_logger.error(f"Error during paystack transfer initiation for user {user.email}: {e}")
           return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
      
      with transaction.atomic():
          # Create a new debit transaction
          Transaction.objects.create(
              vendor=vendor,
              transaction_type='debit',
              amount=amount,
              status='pending',
              account_number=account_number,
              account_full_name=account_full_name,
              phone_number=phone_number,
              bank_name=bank_name,
              paystack_payment_reference=transfer_response['data'].get('transfer_code', None),
          )

           # Update vendor Balance
          profile.wallet_balance -= amount
          profile.save()
          application_logger.info(f"Withdrawal of {amount} initiated by vendor: {user.email}, transfer code is: {transfer_response['data'].get('transfer_code', None)}")
      banks_for_dropdown = get_banks_for_dropdown()

      return Response({'message': 'Withdrawal initiated',
       'new_balance': profile.wallet_balance,
       'transfer_code':transfer_response['data'].get('transfer_code', None),
        'banks': banks_for_dropdown,
       }, status=status.HTTP_200_OK)