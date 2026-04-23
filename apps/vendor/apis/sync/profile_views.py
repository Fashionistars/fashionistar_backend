# apps/vendor/apis/sync/profile_views.py
"""
Vendor Profile API — DRF Sync Views.

URL prefix: /api/v1/vendor/

Endpoints:
  GET    /api/v1/vendor/profile/     — retrieve my store profile
  PATCH  /api/v1/vendor/profile/     — update profile (scalar fields + M2M collections)
  GET    /api/v1/vendor/setup/       — get onboarding setup state
  POST   /api/v1/vendor/setup/       — create/update first-time vendor setup
  POST   /api/v1/vendor/payout/      — save bank / payout details
  POST   /api/v1/vendor/pin/set/     — set 4-digit transaction PIN
  POST   /api/v1/vendor/pin/verify/  — verify 4-digit PIN before payout
"""
import logging

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.permissions import IsVendor
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


class VendorProfileView(APIView):
    """
    GET  /api/v1/vendor/profile/ — retrieve vendor store profile
    PATCH /api/v1/vendor/profile/ — update store profile
    """
    permission_classes = [IsAuthenticated, IsVendor]

    def get(self, request):
        profile = get_vendor_profile_or_none(request.user)
        if profile is None:
            return Response(
                {
                    "status": "error",
                    "message": "Vendor setup is required before profile access.",
                    "code": "vendor_setup_required",
                },
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response({
            "status": "success",
            "message": "Vendor profile retrieved.",
            "data": VendorProfileOutputSerializer(profile).data,
        })

    def patch(self, request):
        serializer = VendorProfileUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            profile = VendorService.update_profile(
                user=request.user,
                data=serializer.validated_data,
            )
        except Exception as exc:
            logger.exception(
                "VendorProfileView.patch: error for user=%s: %s",
                request.user.pk, exc,
            )
            return Response(
                {
                    "status": "error",
                    "message": "Vendor profile update failed. Ensure vendor setup is complete.",
                    "code": "vendor_setup_required",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response({
            "status": "success",
            "message": "Profile updated successfully.",
            "data": VendorProfileOutputSerializer(profile).data,
        })


class VendorSetupStateView(APIView):
    """
    GET  /api/v1/vendor/setup/ — retrieve onboarding setup state
    POST /api/v1/vendor/setup/ — create/update the first vendor setup record
    """
    permission_classes = [IsAuthenticated, IsVendor]

    def get(self, request):
        profile = get_vendor_profile_or_none(request.user)
        if profile is None:
            # Vendor registered but profile not yet provisioned
            return Response({
                "status": "success",
                "data": {
                    "current_step": 1,
                    "completion_percentage": 0,
                    "profile_complete": False,
                    "bank_details": False,
                    "id_verified": False,   # informational
                    "first_product": False,
                    "onboarding_done": False,
                },
            })
        setup = get_vendor_setup_state(profile)
        if setup is None:
            return Response({
                "status": "success",
                "data": {
                    "current_step": 1,
                    "completion_percentage": 0,
                    "profile_complete": False,
                    "bank_details": False,
                    "id_verified": False,
                    "first_product": False,
                    "onboarding_done": False,
                },
            })
        return Response({
            "status": "success",
            "data": VendorSetupStateSerializer(setup).data,
        })

    def post(self, request):
        serializer = VendorSetupSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        profile = VendorProvisioningService.provision(
            request.user,
            data=serializer.validated_data,
        )
        setup = get_vendor_setup_state(profile)

        return Response(
            {
                "status": "success",
                "message": "Vendor setup saved successfully.",
                "data": {
                    "profile": VendorProfileOutputSerializer(profile).data,
                    "setup_state": (
                        VendorSetupStateSerializer(setup).data
                        if setup is not None
                        else None
                    ),
                },
            },
            status=status.HTTP_201_CREATED,
        )


class VendorPayoutView(APIView):
    """
    POST /api/v1/vendor/payout/ — save bank / payout account details
    """
    permission_classes = [IsAuthenticated, IsVendor]

    def post(self, request):
        serializer = VendorPayoutDetailsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            payout = VendorService.save_payout_details(
                user=request.user,
                data=dict(serializer.validated_data),
            )
        except Exception as exc:
            logger.exception(
                "VendorPayoutView.post: error for user=%s: %s",
                request.user.pk, exc,
            )
            return Response(
                {
                    "status": "error",
                    "message": "Payout details save failed. Ensure vendor setup is complete.",
                    "code": "vendor_setup_required",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response({
            "status": "success",
            "message": "Payout details saved.",
            "data": {
                "bank_name":     payout.bank_name,
                "account_name":  payout.account_name,
                "account_last4": payout.account_last4,
                "is_verified":   payout.is_verified,
            },
        }, status=status.HTTP_201_CREATED)


class VendorSetPinView(APIView):
    """
    POST /api/v1/vendor/pin/set/ — set 4-digit payout confirmation PIN
    """
    permission_classes = [IsAuthenticated, IsVendor]

    def post(self, request):
        serializer = VendorTransactionPinSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            VendorService.set_transaction_pin(
                user=request.user,
                raw_pin=serializer.validated_data["pin"],
            )
        except ValueError as exc:
            return Response(
                {"status": "error", "message": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as exc:
            logger.exception("VendorSetPinView.post: error for user=%s: %s", request.user.pk, exc)
            return Response(
                {"status": "error", "message": "PIN update failed."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response({"status": "success", "message": "Transaction PIN set."})


class VendorVerifyPinView(APIView):
    """
    POST /api/v1/vendor/pin/verify/ — verify payout PIN before withdrawal
    """
    permission_classes = [IsAuthenticated, IsVendor]

    def post(self, request):
        serializer = VendorTransactionPinSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        is_valid = VendorService.verify_transaction_pin(
            user=request.user,
            raw_pin=serializer.validated_data["pin"],
        )
        if not is_valid:
            return Response(
                {"status": "error", "message": "Invalid PIN.", "code": "invalid_pin"},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        return Response({"status": "success", "message": "PIN verified."})
