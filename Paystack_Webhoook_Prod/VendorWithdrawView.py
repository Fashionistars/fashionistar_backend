from rest_framework import generics
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated, AllowAny
from vendor.models import Vendor
from Paystack_Webhoook_Prod.models import BankAccountDetails, Transaction
from userauths.models import  Profile, User
from decimal import Decimal
from django.db import transaction
import logging
import json
from Paystack_Webhoook_Prod.serializers__BankAccountDetails import BankAccountDetailsSerializer
from Paystack_Webhoook_Prod.UTILS.utils_TransferRecipient import create_transfer_recipient, fetch_user_and_vendor
from requests.exceptions import ConnectionError, Timeout, RequestException
from django.core.exceptions import MultipleObjectsReturned, ObjectDoesNotExist
from Paystack_Webhoook_Prod.serializers_WITHDRAWAL import  VendorWithdrawSerializer
from Paystack_Webhoook_Prod.UTILS.paystack import Transfer as PaystackTransfer
from rest_framework.exceptions import PermissionDenied
from vendor.utils import fetch_user_and_vendor, vendor_is_owner
# Get logger for application
application_logger = logging.getLogger('application')
# Get logger for paystack
paystack_logger = logging.getLogger('paystack')

class VendorWithdrawView(generics.CreateAPIView):
    """
     API endpoint for vendors to initiate a withdrawal from their wallet.
    *   *URL:* /api/vendor/withdraw/
    *   *Method:* POST
    *   *Authentication:* Requires a valid authentication token in the Authorization header.
        *    *Request Body (JSON):*
            json
                {
                "amount": 50, // The amount to withdraw (positive decimal)
                "transaction_password": "1234", // Vendor's transaction password for security
                "bank_details_id": "12345", // The id of the bank details
                "reason": "For my Expenses" // Optional reason for withdrawal
                }
                 
                 *  amount: (Decimal, required) The amount the vendor wants to withdraw from their wallet. Must be a positive value.
                 *  transaction_password: (string, required) The transaction password for the vendor.
                 *  bank_details_id (string, required): The id of the bank details from the VendorBankDetailsListView to use for the transfer.
                 *    reason (string, optional): The vendors reason for withdrawal.
          *   *Response (JSON):*
              *  On success (HTTP 200 OK):
                      json
                         {
                           "message": "Withdrawal initiated",
                           "new_balance": 120.00,
                            "transfer_code": "TRF_xxx", // The transfer code from paystack
                            "data": {...}
                         }
                      
               *  On failure (HTTP 400, 404 or 500):
                      json
                         {
                            "error": "Error message" // The error message detailing the failure.
                         }
                        
                      Possible error messages:
                        *    "All fields are required: 'amount', 'transaction_password' and 'bank_details_id'.": if any required field is missing from the request body.
                        *    "Amount must be positive": If amount is not a positive number.
                        *    "Invalid amount format": If the amount entered is not a number.
                         *   "Vendor not found": If the vendor is not found.
                         *   "Transaction password not set. Please set it first.": If the transaction password has not been set for the vendor.
                        *   "Invalid transaction password": If an incorrect transaction password was provided.
                        *  "Insufficient balance": If the vendor's balance is lower than the withdrawal amount.
                        *  "Bank details not found": If no bank details is found with that ID.
                        *  "Failed to initiate transfer on paystack {paystack_error_message}": If the paystack transfer request fails, includes the paystack error message
                        *   "Failed to initiate transfer. Please check your internet connection or try again.": If there is any connection error to the paystack servers.
                         *  "Invalid user role": If the user role is not vendor.
    """
    serializer_class = VendorWithdrawSerializer
    permission_classes = (IsAuthenticated,)
  
    @transaction.atomic
    def create(self, request, *args, **kwargs):
        """
        Handles the creation of a withdrawal request
        """
        serializer = self.get_serializer(data=request.data)
        if not serializer.is_valid():
            application_logger.error(f"Invalid input data for withdrawal: {serializer.errors}")
            return Response({'error': serializer.errors}, status=status.HTTP_400_BAD_REQUEST)
        
        user = request.user
        amount = serializer.validated_data.get('amount')
        transaction_password = serializer.validated_data.get('transaction_password')
        bank_details_id = serializer.validated_data.get('bank_details_id')
        reason = serializer.validated_data.get('reason')
        
        try:
            user_obj, vendor_obj, error_response = fetch_user_and_vendor(user)
            if error_response:
                application_logger.error(f"Error fetching user or vendor: {error_response}")
                return Response({'error': error_response}, status=status.HTTP_404_NOT_FOUND)
            
            if user_obj.role != 'vendor':
                 application_logger.error(f"User: {user.email} is not a vendor")
                 return Response({'error': "You are not a vendor"}, status=status.HTTP_400_BAD_REQUEST)
            


            try:
                bank_details = BankAccountDetails.objects.get(id=bank_details_id)
                vendor_is_owner(vendor_obj, obj=bank_details)
            except BankAccountDetails.DoesNotExist:
                application_logger.error(f"Bank details with id: {bank_details_id} not found for user {user.email}")
                return Response({'error': 'Bank details not found'}, status=status.HTTP_404_NOT_FOUND)
            

            if not vendor_obj.transaction_password:
               application_logger.error(f"Transaction password not set for vendor: {user.email}")
               return Response(
                {
                 "message": "Transaction password not set. Please set it first.",
                 "redirect_url": "/set-transaction-password/"
                 },
                 status=status.HTTP_302_FOUND
               )


            if not vendor_obj.check_transaction_password(transaction_password):
                application_logger.error(f"Invalid transaction password entered for user {user.email}")
                return Response({'error': 'Invalid transaction password'}, status=status.HTTP_400_BAD_REQUEST)

            if vendor_obj.wallet_balance < amount:
                 application_logger.error(f"Insufficient balance for withdrawal for vendor {user.email}")
                 return Response({'error': 'Insufficient balance'}, status=status.HTTP_400_BAD_REQUEST)


            with transaction.atomic():

                # ================== MOST IMPORTANT CODE TO WORK WITH  FOR LOCKING THE VENDOR'S RELATED DATABASE INSTANCE WHILE PERFORMING A TRANSACTION BUSINESS ON THE VENDOR'S DATABASE COLUMNS ================

                # Update vendor Balance
                vendor_obj = Vendor.objects.select_for_update().get(pk=vendor_obj.pk)
                vendor_obj.wallet_balance -= amount
                vendor_obj.save()

                application_logger.info(f"Withdrawal of {amount} initiated by vendor: {user.email}")

                # ================== MOST IMPORTANT CODE TO WORK WITH  FOR LOCKING THE VENDOR'S RELATED DATABASE INSTANCE WHILE PERFORMING A TRANSACTION BUSINESS ON THE VENDOR'S DATABASE COLUMNS ================




                

                # Create a new debit transaction
                transaction_obj = Transaction.objects.create(
                    vendor=vendor_obj,
                    transaction_type='debit',
                    amount=amount,
                    status='pending',
                    description=reason if reason else None,
                   
                )

                #initialize transfer
                paystack_transfer = PaystackTransfer(amount=amount, recipient_code=bank_details.paystack_Recipient_Code)
                transfer_response = paystack_transfer.initiate_transfer()
                print(transfer_response)

                if not transfer_response['status']:
                    paystack_logger.error(f"Failed to transfer funds for user: {user.email}, paystack error response: {transfer_response}")
                    message = transfer_response.get('message', 'An unexpected error occurred with Paystack.')
                    #check if the message is a json
                    try:
                        message_json = json.loads(message)
                        if isinstance(message_json, dict) and message_json.get('message'):
                            message = message_json['message']
                               
                    except json.JSONDecodeError:
                        pass  # do nothing, just use the normal message

                    #Rollback the transaction if paystack fails
                    transaction_obj.status = "failed"
                    transaction_obj.save()
                    vendor_obj.wallet_balance += amount
                    vendor_obj.save()
                    return Response({"error": f"Failed to initiate transfer on paystack {message}"}, status=status.HTTP_400_BAD_REQUEST)
                
                #update the transfer_code in transaction record
                transaction_obj.paystack_payment_reference = transfer_response['data'].get('reference', None)
                transaction_obj.paystack_transfer_code = transfer_response['data'].get('transfer_code', None)
                transaction_obj.save()
                application_logger.info(f"Withdrawal of {amount} initiated by vendor: {user.email}, transfer code is: {transfer_response['data'].get('transfer_code', None)}")


                return Response({
                    'message': 'Withdrawal initiated',
                    'new_balance': vendor_obj.wallet_balance,
                    'transfer_code':transfer_response['data'].get('transfer_code', None),
                    'data': serializer.data
                    }, status=status.HTTP_200_OK)

        except PermissionDenied as e:
            application_logger.error(f"Permission denied: {e} for vendor {user.email}")
            return Response(
                {'error': f'You do not have permission to perform this action.',
                'Reason' : f'{vendor_obj.name} is not the owner of This Object  ~  {bank_details}'
                }, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            application_logger.error(f"An error occurred: {e} for user {user.email}")
            return Response({'error': f"An error occurred, please check your input or contact support. {e}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)



