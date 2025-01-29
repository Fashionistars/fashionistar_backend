from rest_framework import generics
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from vendor.models import Vendor
from Paystack_Webhoook_Prod.models import BankAccountDetails
from userauths.models import User
from django.db import transaction
import logging
import json
from Paystack_Webhoook_Prod.serializers__BankAccountDetails import BankAccountDetailsSerializer
from Paystack_Webhoook_Prod.UTILS.utils_TransferRecipient import create_transfer_recipient, fetch_user_and_vendor,update_transfer_recipient, delete_transfer_recipient, fetch_transfer_recipient, validate_bank_details
from requests.exceptions import ConnectionError, Timeout, RequestException
from django.core.exceptions import MultipleObjectsReturned, ObjectDoesNotExist
from rest_framework.pagination import PageNumberPagination
from datetime import datetime

# Get logger for application
application_logger = logging.getLogger('application')
# Get logger for paystack
paystack_logger = logging.getLogger('paystack')




class VendorBankDetailsCreateView(generics.CreateAPIView):
    """
        API endpoint for vendors to create and save their bank account details.
         *   **URL:** `/api/vendor/bank-details/`
        *   **Method:** `POST`
        *   **Authentication:** Requires a valid authentication token in the `Authorization` header.
        *   **Request Body (JSON):**
                ```json
                    {
                    "account_number": "1234567890",  // Vendor's bank account number
                    "account_full_name": "John Doe",  // Vendor's bank account full name
                    "bank_name": "Access Bank",   // The bank where the user wants to withdraw the funds
                    }
                    ```
                 *  `account_number`: (string, required) The account number where the user is withdrawing to. Must contain only digits and be exactly 10 digits long.
                 *  `account_full_name`: (string, required) The full name on the account provided.
                 *  `bank_name`: (string, required) The bank name which should match the values in `BANKS_LIST`.
           *   **Response (JSON):**
             *   On success (HTTP 201 Created):
                        ```json
                        {
                        "message": "Bank details created successfully", // Success message
                         "data": {...} // The bank details that was created with the paystack recipient code
                        }
                       ```
                *   On failure (HTTP 400 Bad Request):
                     ```json
                     {
                         "error": "Error message" // Error message explaining the failure
                     }
                     ```
                  Possible error messages:
                   *  `"All fields are required: 'account_number', 'account_full_name', and 'bank_name'."`: if any required field is missing from the request body.
                  *   `"Account number must contain only numbers."`: if account number contains other characters than numbers.
                   *   `"Account number must be exactly 10 digits."`: if the account number length is not equal to 10.
                  *  `"Invalid bank name"`: if the bank name does not match the bank names in `BANK_CHOICES`.
                  *  `"Failed to create transfer recipient. {paystack_error_message}"`:  if there is an error creating the transfer recipient on Paystack. Paystack error messages will be similar to these :
                        *   `"Invalid bank account number"`: if the account number is not valid for that bank.
                        *   `"Invalid account name"`: if the account name does not match the account name registered with the bank.
                         *   `"The bank is currently unavailable"`: if there is an issue with the receiving bank.
                  *  `"Failed to create transfer recipient. Please check your internet connection or try again."`: if there is any connection error to the paystack servers.
                   *  `"Either a user or a vendor must be provided, but not both."`: if both user and vendor were provided or neither were.
        
        * On success (HTTP 200 OK):
                         ```json
                         {
                           "message": "Bank details updated successfully",
                           "data": {...} // The bank details with the paystack recipient code
                         }
                         ```
    """
    serializer_class = BankAccountDetailsSerializer
    permission_classes = [IsAuthenticated]
   
    @transaction.atomic
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        if not serializer.is_valid():
            application_logger.error(f"Invalid input data for bank details creation: {serializer.errors}")
            return Response({'error': serializer.errors}, status=status.HTTP_400_BAD_REQUEST)
            
        user = self.request.user
        # Validate the data
        account_number = serializer.validated_data.get('account_number')
        account_full_name = serializer.validated_data.get('account_full_name')
        bank_name = serializer.validated_data.get('bank_name')
        

        if not all([account_number, account_full_name, bank_name]):
            application_logger.error(f"Bank details creation failed, all required fields are missing or not valid for user {user.email}")
            return Response({'error': "All fields are required: 'account_number', 'account_full_name', and 'bank_name'."}, status=status.HTTP_400_BAD_REQUEST)
        
        if not isinstance(account_number, str) or not account_number.isdigit():
            application_logger.error(f"Bank details creation failed, Account number is not a valid number for user {user.email}")
            return Response({'error': "Account number must contain only numbers."}, status=status.HTTP_400_BAD_REQUEST)
        
        if len(account_number) != 10:
            application_logger.error(f"Bank details creation failed, Account number is not up to 10 digits for user {user.email}")
            return Response({'error': "Account number must be exactly 10 digits."}, status=status.HTTP_400_BAD_REQUEST)



        try:

            user_obj, vendor_obj, error_response = fetch_user_and_vendor(user)
            if error_response:
                return Response({'error': error_response}, status=status.HTTP_404_NOT_FOUND)
            
            if user_obj.role == 'vendor':
                # Use Paystack API to create recipient
                bank_code = serializer.validated_data.get('bank_code')
                recipient_data = {
                "type": "nuban",
                "name": account_full_name,
                "account_number": account_number,
                    "bank_code": bank_code,
                }
                paystack_logger.info(f"Payload for creating transfer recipient: {recipient_data}")
                try:
                    recipient_response = create_transfer_recipient(recipient_data)
                    if recipient_response['status'] is False:
                        paystack_logger.error(f"Failed to create transfer recipient for vendor {user.email}, REASON: The account number you provided is not valid for the bank you selected. Please re-check the account number and try again.")
                        
                        message = recipient_response.get('message', 'An unexpected error occurred with Paystack.')
                        #check if the message is a json
                        try:
                                message_json = json.loads(message)
                                if isinstance(message_json, dict) and message_json.get('message'):
                                    message = message_json['message']
                                
                        except json.JSONDecodeError:
                            pass  # do nothing, just use the normal message
                        
                        if "Invalid bank account number" in message:
                            message = "The account number you provided is not valid for the bank you selected. Please re-check the account number and try again."
                        elif "Invalid account name" in message:
                            message = "The account name does not match the account number you provided. Please re-check the account name and try again."
                        elif "The bank is currently unavailable" in message:
                            message = "The selected bank is currently unavailable, please try again later."
                        else:
                                message = f"Failed to create transfer recipient. {message}"
                        
                        return Response(
                            {'error': "The account number you provided is not valid for the bank you selected. Please re-check the account number and try again."},
                            status=status.HTTP_400_BAD_REQUEST
                            )
                    recipient_code = recipient_response['data']['recipient_code']
                        
                    # Check if recipient code already exists
                    bank_details = BankAccountDetails.objects.filter(paystack_Recipient_Code=recipient_code).first()
                    if bank_details:
                        paystack_logger.info(f"Transfer recipient Retrieved for vendor {user.email}, recipient code is {recipient_code}")

                        bank_details.account_number = recipient_response['data']['details'].get('account_number')
                        bank_details.account_full_name = recipient_response['data'].get('name')
                        bank_details.bank_name = recipient_response['data']['details'].get('bank_name')
                        bank_details.bank_code = recipient_response['data']['details'].get('bank_code')
                        bank_details.updated = datetime.fromisoformat(recipient_response['data']['updatedAt'].replace("Z", "+00:00"))
                        bank_details.save()
                        
                        application_logger.info(f"Updated bank details for vendor profile {user.email}, with id {bank_details.id}")
                        return Response(
                                    {
                                    'message': 'Bank details updated successfully',
                                    'data': {
                                        "Account Number"  : bank_details.account_number,
                                        "Account Name"  : bank_details.account_full_name,
                                        "Bank Name"  : bank_details.bank_name,
                                        },
                                    },
                                    status=status.HTTP_200_OK
                                )


                    paystack_logger.info(f"Transfer recipient created for vendor {user.email}, recipient code is {recipient_code}")
                    # Save the details if it does not exist.
                    serializer.save(
                        vendor=vendor_obj, 
                        paystack_Recipient_Code=recipient_code,
                        bank_code = recipient_response['data']['details'].get('bank_code'),
                        account_number=recipient_response['data']['details'].get('account_number'),
                        account_full_name=recipient_response['data'].get('name'),
                        bank_name=recipient_response['data']['details'].get('bank_name'),
                        updated = datetime.fromisoformat(recipient_response['data']['updatedAt'].replace("Z", "+00:00"))
                    )
                    
                    application_logger.info(f"Successfully saved bank details to vendor profile {user.email}")
                    return Response(
                        {'message': 'Bank details created successfully',
                        'data': {
                            "Account Number"  : bank_details.account_number,
                            "Account Name"  : bank_details.account_full_name,
                            "Bank Name"  : bank_details.bank_name,
                            },
                        },
                        status=status.HTTP_201_CREATED
                    )
                except (ConnectionError, Timeout, RequestException) as e:
                        paystack_logger.error(f"Failed to create transfer recipient for vendor {user.email}, paystack error response: {e}")
                        return Response(
                        {'error': f"Failed to create transfer recipient. Please check your internet connection or try again."},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        )
            elif user_obj.role == 'client':
                serializer.save(user=user_obj)
                application_logger.info(f"Successfully saved bank details to client profile {user.email}")
                return Response(
                        {'message': 'Bank details created successfully',
                        'data': serializer.data
                        },
                        status=status.HTTP_201_CREATED
                    )
            else:
                application_logger.error(f"Invalid user role: {user_obj.role}, expected client or vendor")
                return Response({'error': 'Invalid user role'}, status=status.HTTP_400_BAD_REQUEST)

        except Exception as e:
            application_logger.error(f"An error occurred: {e} for user {user.email}")
            return Response({'error': f"An error occurred, please check your input or contact support. {e}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)





class VendorBankDetailsUpdateView(generics.RetrieveUpdateAPIView):
    """
     API endpoint for vendors to update their bank account details.
    *   **URL:** `/api/vendor/bank-details/<str:pk>`
    *   **Method:** `PUT`
    *   **Authentication:** Requires a valid authentication token in the `Authorization` header.
        *    **Request Body (JSON):**
            ```json
                {
                "account_number": "1234567890",  // Vendor's bank account number
                "account_full_name": "John Doe",  // Vendor's bank account full name
                 "bank_name": "Access Bank",   // The bank where the user wants to withdraw the funds
                }
                 ```
                 *  `account_number`: (string, optional) The account number where the user is withdrawing to. Must contain only digits and be exactly 10 digits long.
                 *  `account_full_name`: (string, optional) The full name on the account provided.
                 *  `bank_name`: (string, optional) The bank name which should match the values in `BANKS_LIST`.
          *   **Response (JSON):**
              *  On success (HTTP 200 OK):
                      ```json
                         {
                           "message": "Bank details updated successfully",
                           "data": {...} // The bank details with the paystack recipient code
                         }
                      ```
               *  On failure (HTTP 400 or 404):
                      ```json
                         {
                            "error": "Error message" // The error message detailing the failure.
                         }
                        ```
                      Possible error messages:
                        *   `"Bank details not found"`: if no bank details is found with the id provided.
                       *  `"All fields are required: 'account_number', 'account_full_name', and 'bank_name'."`: if any required field is missing from the request body.
                       *  `"Account number must contain only numbers."`: if account number contains other characters than numbers.
                       *  `"Account number must be exactly 10 digits."`: if the account number length is not equal to 10.
                       * `"Invalid bank name"`: if the bank name does not match the bank names in `BANK_CHOICES`.
                      *  `"Failed to update transfer recipient. {paystack_error_message}"`: if there is an error updating the transfer recipient on Paystack. Paystack error messages will be similar to these :
                            *   `"Invalid bank account number"`: if the account number is not valid for that bank.
                            *   `"Invalid account name"`: if the account name does not match the account name registered with the bank.
                            *   `"The bank is currently unavailable"`: if there is an issue with the receiving bank.
                       *  `"Failed to update transfer recipient. Please check your internet connection or try again."`: if there is any connection error to the paystack servers.
    """
    serializer_class = BankAccountDetailsSerializer
    permission_classes = [IsAuthenticated]
    queryset = BankAccountDetails.objects.all()
    lookup_field = 'pk'

    def perform_update(self, serializer):
          user = self.request.user

          # Validate the data
          validation_error = validate_bank_details(serializer.validated_data)
          if validation_error:
              return Response({'error': validation_error}, status=status.HTTP_400_BAD_REQUEST)
          
          user_obj, vendor_obj, error_response = fetch_user_and_vendor(user)
          if error_response:
               return Response({'error': error_response}, status=status.HTTP_404_NOT_FOUND)
          
          if user_obj.role == 'vendor':
            try:
                bank_details = self.get_object()
            except BankAccountDetails.DoesNotExist:
                return Response({'error': 'Bank details not found'}, status=status.HTTP_404_NOT_FOUND)
            
            if bank_details.paystack_Recipient_Code:
                recipient_data = {
                    "name": serializer.validated_data.get('account_full_name'),
                }
                try:
                    recipient_response = update_transfer_recipient(bank_details.paystack_Recipient_Code, recipient_data)
                    if recipient_response['status'] is False:
                        paystack_logger.error(f"Failed to update transfer recipient for vendor {user.email},  paystack response: {recipient_response}")
                        message = recipient_response.get('message', 'An unexpected error occurred with Paystack.')

                        #check if the message is a json
                        try:
                             message_json = json.loads(message)
                             if isinstance(message_json, dict) and message_json.get('message'):
                                 message = message_json['message']
                             
                        except json.JSONDecodeError:
                            pass  # do nothing, just use the normal message
                        
                        if "Invalid bank account number" in message:
                            message = "The account number you provided is not valid for the bank you selected. Please re-check the account number and try again."
                        elif "Invalid account name" in message:
                            message = "The account name does not match the account number you provided. Please re-check the account name and try again."
                        elif "The bank is currently unavailable" in message:
                            message = "The selected bank is currently unavailable, please try again later."
                        else:
                             message = f"Failed to create transfer recipient. {message}"
                        return Response(
                                {'error': message,
                                'paystack_response': recipient_response}, status=status.HTTP_400_BAD_REQUEST
                            )
                    paystack_logger.info(f"Successfully updated transfer recipient for vendor {user.email}, response is {recipient_response}")
                    
                    bank_details.account_number = serializer.validated_data.get('account_number')
                    bank_details.account_full_name = serializer.validated_data.get('account_full_name')
                    bank_details.bank_name = serializer.validated_data.get('bank_name')
                   
                    
                    
                    serializer.instance = bank_details
                    
                    application_logger.info(f"Successfully updated bank details for vendor {user.email} with the id {self.kwargs['pk']}")
                    return Response(
                    {'message': 'Bank details updated successfully',
                     'data': {
                            "Account Number"  : bank_details.account_number,
                            "Account Name"  : bank_details.account_full_name,
                            "Bank Name"  : bank_details.bank_name,
                            },
                     }, status=status.HTTP_200_OK
                    )
                except (ConnectionError, Timeout, RequestException) as e:
                      paystack_logger.error(f"Failed to update transfer recipient for vendor {user.email}, paystack error response: {e}")
                      return Response(
                      {'error': f'Failed to update transfer recipient. Please check your internet connection or try again.'},
                      status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                 )
          elif user_obj.role == 'client':
                serializer.save(user=user_obj)
                application_logger.info(f"Successfully updated bank details for client {user.email} with the id {self.kwargs['pk']}")
                return Response(
                {'message': 'Bank details updated successfully',
                 'data': serializer.data
                 }, status=status.HTTP_200_OK
                )
          else:
             application_logger.error(f"Invalid user role: {user_obj.role}, expected client or vendor")
             return Response({'error': 'Invalid user role'}, status=status.HTTP_400_BAD_REQUEST)









class VendorBankDetailsPagination(PageNumberPagination):
    """
    Custom pagination class for vendor bank details. Returns 5 items per page.
    """
    page_size = 5
    page_size_query_param = 'page_size'
    max_page_size = 10



class VendorBankDetailsListView(generics.ListAPIView):
    """
    API endpoint for retrieving a list of bank details for a particular vendor.

     *   **URL:** `/api/vendor/bank-details/list/`
        *   **Method:** `GET`
        *   **Authentication:** Requires a valid authentication token in the `Authorization` header.
        *   **Request Body:** None
        *   **Response (JSON):**
                *   On success (HTTP 200 OK):
                    ```json
                    {
                       "count": 1, // The number of bank details found
                        "next": null,
                        "previous": null,
                        "results": [
                            {
                            "id": "7f50d35d-02a4-4b56-8c7b-b0f7b08c371b",
                            "user": null,
                            "vendor": "ee82962d-6116-49eb-ac26-c76723e87d85",
                            "account_number": "9087654321",
                            "account_full_name": "AL-FASHIONISTARCLOTHINGS LIMITED",
                            "bank_name": "Access Bank (Diamond)",
                            "paystack_Recipient_Code": "RCP_18902hdyusn72a"
                           },
                                ...
                         ]
                     }
                    ```
                    *   `count`: (Integer) The total number of bank details found.
                    *  `next`:  (string, optional) Link to the next page.
                     *   `previous`: (string, optional) Link to the previous page.
                     *   `results`: (Array) An array of bank details objects. The `id` of each object is what the frontend should use as a bank_details_id in the withdraw endpoint.
                *   On failure (HTTP 404):
                    ```json
                       {
                            "error": "Vendor not found" // Message if the vendor profile could not be found.
                         }
                       ```
                        *   `"Bank details not found"`: If no bank details were found for the vendor or user.
    """
    serializer_class = BankAccountDetailsSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = VendorBankDetailsPagination

    def get_queryset(self):
        user = self.request.user
        user_obj, vendor_obj, error_response = fetch_user_and_vendor(user)
        if error_response:
            return BankAccountDetails.objects.none() # Return empty queryset
            # return Response({'error': error_response}, status=status.HTTP_404_NOT_FOUND)

        try:
            if user_obj.role == 'vendor':
                 queryset = BankAccountDetails.objects.filter(vendor=vendor_obj).order_by('-timestamp')
            else:
                 queryset = BankAccountDetails.objects.filter(user=user_obj).order_by('-timestamp')
            
            if not queryset.exists():
                application_logger.info(f"No bank details found for user {user.email}")
                # return Response({'error': 'Bank details not found'}, status=status.HTTP_404_NOT_FOUND)
                return BankAccountDetails.objects.none()  # Return empty queryset
            return queryset

        except Exception as e:
             application_logger.error(f"Error while fetching bank details for user {user.email}: {e}")
             return BankAccountDetails.objects.none()   # Return empty queryset
             #return Response({'error': f'An error occurred while fetching bank details: {e}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    




class VendorBankDetailsDetailView(generics.RetrieveAPIView):
   
    serializer_class = BankAccountDetailsSerializer
    permission_classes = [IsAuthenticated]
    queryset = BankAccountDetails.objects.all()
    lookup_field = 'pk'

    def retrieve(self, request, *args, **kwargs):
      try:
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        application_logger.info(f"Successfully retrieved bank details with id: {self.kwargs['pk']} for user: {request.user.email}")
        return Response(serializer.data, status=status.HTTP_200_OK)
      except BankAccountDetails.DoesNotExist:
            application_logger.error(f"Bank details with id: {self.kwargs['pk']} not found for user {request.user.email}")
            return Response({'error': 'Bank details not found'}, status=status.HTTP_404_NOT_FOUND)
        










class VendorBankDetailsDeleteView(generics.DestroyAPIView):
    """
     API endpoint for vendors to delete their bank account details.
      *   **URL:** `/api/vendor/bank-details/<str:pk>`
      *   **Method:** `DELETE`
      *   **Authentication:** Requires a valid authentication token in the `Authorization` header.
       *   **Response (JSON):**
              *  On success (HTTP 204 No Content):
                      ```json
                        {} // No content
                      ```
                *  On failure (HTTP 404 Not Found):
                      ```json
                         {
                            "error": "Error message" // Error message detailing the failure
                         }
                    ```
                     Possible error messages:
                     *   `"Bank details not found"`: If no bank details was found with the id provided.
                     *   `"Failed to delete transfer recipient. {paystack_error_message}"`: if there is an error deleting the transfer recipient on Paystack.
                      *  `"Failed to delete transfer recipient. Please check your internet connection or try again."`: if there is any connection error to the paystack servers.
    """
    serializer_class = BankAccountDetailsSerializer
    permission_classes = [IsAuthenticated]
    queryset = BankAccountDetails.objects.all()
    lookup_field = 'pk'

    def perform_destroy(self, instance):
        user = self.request.user
        try:
           if instance.paystack_Recipient_Code:
              recipient_response = delete_transfer_recipient(instance.paystack_Recipient_Code)
              if recipient_response['status'] is False:
                 paystack_logger.error(f"Failed to delete transfer recipient for vendor {user.email}, paystack response is {recipient_response}")
                 message = recipient_response.get('message', 'An unexpected error occurred with Paystack.')
                 
                 #check if the message is a json
                 try:
                      message_json = json.loads(message)
                      if isinstance(message_json, dict) and message_json.get('message'):
                          message = message_json['message']
                             
                 except json.JSONDecodeError:
                    pass  # do nothing, just use the normal message
                 return Response(
                  {'error': f'Failed to delete transfer recipient: {message}',
                  'paystack_response': recipient_response}, status=status.HTTP_400_BAD_REQUEST
                        )
              paystack_logger.info(f"Successfully deleted transfer recipient for vendor {user.email}, response is {recipient_response}")
           instance.delete()
           application_logger.info(f"Successfully deleted bank details for vendor {user.email}, with id: {self.kwargs['pk']}")
           return Response(status=status.HTTP_204_NO_CONTENT)
        except Exception as e:
              application_logger.error(f"An error occurred while deleting bank details for vendor {user.email} with id: {self.kwargs['pk']}: {e}")
              return Response({'error': f'An error occurred: {e}'}, status=status.HTTP_400_BAD_REQUEST)















