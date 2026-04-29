# apps/vendor/apis/sync/profile_views.py
"""
Vendor Profile API — DRF Sync Views
===================================

Manages the core identity and financial configuration of a Vendor.
Includes onboarding setup, profile updates, and secure payout configuration.

URL prefix: /api/v1/vendor/

Design Principles:
  - Provisioning: Enforces a structured onboarding flow via VendorProvisioningService.
  - Security: Uses 4-digit PIN verification for sensitive payout updates.
  - Resilience: Decouples profile logic from user auth via the selector layer.
"""

import logging
from rest_framework import status
from rest_framework.generics import GenericAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.renderers import BrowsableAPIRenderer

from apps.common.renderers import CustomJSONRenderer
from apps.common.responses import success_response, error_response
from apps.common.permissions import IsVendor, IsVendorWithProfile
from apps.vendor.selectors.vendor_selectors import (
    get_vendor_profile_or_none,
    get_vendor_setup_state,
)
from apps.vendor.serializers.profile_serializers import (
    VendorPayoutDetailsSerializer,
    VendorProfileOutputSerializer,
    VendorSetupSerializer,
    VendorProfileUpdateSerializer,
    VendorSetupStateSerializer,
    VendorTransactionPinSerializer,
)
from apps.vendor.services.vendor_provisioning_service import VendorProvisioningService
from apps.vendor.services.vendor_service import VendorService

logger = logging.getLogger(__name__)


# ===========================================================================
# PROFILE MANAGEMENT
# ===========================================================================


class VendorProfileView(GenericAPIView):
    """
    Retrieves or updates the vendor's store profile.

    Validation Logic:
      - GET: Verifies if vendor setup is complete before returning profile.
      - PATCH: Validates shop name, description, and contact info.

    Security:
      - Requires IsAuthenticated + IsVendor.

    Status Codes:
      200 OK: Data returned/updated.
      404 Not Found: Profile missing (Setup required).
    """
    permission_classes = [IsAuthenticated, IsVendorWithProfile]
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]
    
    def get_serializer_class(self):
        if self.request.method == "PATCH":
            return VendorProfileUpdateSerializer
        return VendorProfileOutputSerializer

    def get(self, request, *args, **kwargs):
        profile = get_vendor_profile_or_none(request.user)
        if profile is None:
            return error_response(
                message="Vendor setup is required before profile access.",
                code="vendor_setup_required",
                status=status.HTTP_404_NOT_FOUND,
            )
        serializer = VendorProfileOutputSerializer(profile)
        return success_response(data=serializer.data)

    def patch(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            profile = VendorService.update_profile(
                user=request.user,
                data=serializer.validated_data,
            )
            output_serializer = VendorProfileOutputSerializer(profile)
            return success_response(data=output_serializer.data, message="Profile updated successfully.")
        except Exception as exc:
            logger.exception("VendorProfileView.patch: error for user=%s: %s", request.user.pk, exc)
            return error_response(
                message="Vendor profile update failed. Ensure vendor setup is complete.",
                code="vendor_setup_required",
                status=status.HTTP_400_BAD_REQUEST,
            )


# ===========================================================================
# ONBOARDING SETUP
# ===========================================================================


class VendorSetupStateView(GenericAPIView):
    """
    Tracks the vendor's progress through the onboarding multi-step flow.

    Flow:
      1. Register -> 2. Shop Details -> 3. Bank Account -> 4. ID Upload.

    Status Codes:
      200 OK: Returns progress percentage and step markers.
      201 Created: Initial profile provisioned.
    """
    permission_classes = [IsAuthenticated, IsVendor]
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]
    
    def get_serializer_class(self):
        if self.request.method == "POST":
            return VendorSetupSerializer
        return VendorSetupStateSerializer

    def get(self, request, *args, **kwargs):
        profile = get_vendor_profile_or_none(request.user)
        if profile is None:
            data = {
                "current_step": 1, "completion_percentage": 0, "profile_complete": False,
                "bank_details": False, "id_verified": False, "first_product": False, "onboarding_done": False,
            }
            return success_response(data=data)
            
        setup = get_vendor_setup_state(profile)
        if setup is None:
            data = {
                "current_step": 1, "completion_percentage": 0, "profile_complete": False,
                "bank_details": False, "id_verified": False, "first_product": False, "onboarding_done": False,
            }
            return success_response(data=data)
            
        serializer = VendorSetupStateSerializer(setup)
        return success_response(data=serializer.data)

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        profile = VendorProvisioningService.provision(request.user, data=serializer.validated_data)
        setup = get_vendor_setup_state(profile)

        data = {
            "profile": VendorProfileOutputSerializer(profile).data,
            "setup_state": VendorSetupStateSerializer(setup).data if setup else None,
        }
        return success_response(data=data, message="Vendor setup completed successfully.", status=status.HTTP_201_CREATED)


# ===========================================================================
# FINANCIAL CONFIGURATION
# ===========================================================================


class VendorPayoutView(GenericAPIView):
    """
    Secures the vendor's bank account details for revenue withdrawal.

    Validation Logic:
      - Validates account number length and bank routing codes.
    """
    permission_classes = [IsAuthenticated, IsVendorWithProfile]
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]
    serializer_class = VendorPayoutDetailsSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            payout = VendorService.save_payout_details(user=request.user, data=dict(serializer.validated_data))
            data = {
                "bank_name":     payout.bank_name,
                "account_name":  payout.account_name,
                "account_last4": payout.account_last4,
                "is_verified":   payout.is_verified,
            }
            return success_response(data=data, message="Payout details saved successfully.", status=status.HTTP_201_CREATED)
        except Exception as exc:
            logger.exception("VendorPayoutView.post: error for user=%s: %s", request.user.pk, exc)
            return error_response(
                message="Payout details save failed. Ensure vendor setup is complete.",
                code="vendor_setup_required",
                status=status.HTTP_400_BAD_REQUEST,
            )


# ===========================================================================
# SECURITY (TRANSACTION PIN)
# ===========================================================================


class VendorSetPinView(GenericAPIView):
    """
    Sets a 4-digit security PIN used for authorizing wallet withdrawals.

    Validation Logic:
      - Enforces exactly 4 numeric digits.
    """
    permission_classes = [IsAuthenticated, IsVendorWithProfile]
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]
    serializer_class = VendorTransactionPinSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            VendorService.set_transaction_pin(user=request.user, raw_pin=serializer.validated_data["pin"])
            return success_response(message="Transaction PIN set successfully.")
        except ValueError as exc:
            return error_response(message=str(exc), status=status.HTTP_400_BAD_REQUEST)
        except Exception as exc:
            logger.exception("VendorSetPinView.post: error for user=%s: %s", request.user.pk, exc)
            return error_response(message="PIN update failed.", status=status.HTTP_400_BAD_REQUEST)


class VendorVerifyPinView(GenericAPIView):
    """
    Verifies the transaction PIN during withdrawal attempts.

    Security:
      - Uses constant-time comparison to prevent timing attacks.
    """
    permission_classes = [IsAuthenticated, IsVendorWithProfile]
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]
    serializer_class = VendorTransactionPinSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        is_valid = VendorService.verify_transaction_pin(user=request.user, raw_pin=serializer.validated_data["pin"])
        if not is_valid:
            return error_response(message="Invalid PIN.", code="invalid_pin", status=status.HTTP_401_UNAUTHORIZED)
        return success_response(message="PIN verified successfully.")
