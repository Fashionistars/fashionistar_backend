
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




from django.conf import settings
import json
import os


# Get logger for application
application_logger = logging.getLogger('application')








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



