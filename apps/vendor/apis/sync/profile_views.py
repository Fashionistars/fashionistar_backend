# apps/vendor/apis/sync/profile_views.py
"""
Vendor Profile API — DRF Sync Views.

URL prefix: /api/v1/vendor/

Endpoints:
  GET    /api/v1/vendor/profile/     — retrieve my store profile
  PATCH  /api/v1/vendor/profile/     — update profile
  GET    /api/v1/vendor/setup/       — get onboarding setup state
  POST   /api/v1/vendor/payout/      — save bank / payout details
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
    VendorProfileUpdateSerializer,
    VendorSetupStateSerializer,
)
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
            profile = VendorService.get_profile(request.user)
        return Response({
            "status": "success",
            "message": "Vendor profile retrieved.",
            "data": VendorProfileOutputSerializer(profile).data,
        })

    def patch(self, request):
        serializer = VendorProfileUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        profile = VendorService.update_profile(
            user=request.user,
            data=serializer.validated_data,
        )
        return Response({
            "status": "success",
            "message": "Profile updated successfully.",
            "data": VendorProfileOutputSerializer(profile).data,
        })


class VendorSetupStateView(APIView):
    """
    GET /api/v1/vendor/setup/ — retrieve onboarding setup state
    """
    permission_classes = [IsAuthenticated, IsVendor]

    def get(self, request):
        profile = get_vendor_profile_or_none(request.user)
        if profile is None:
            profile = VendorService.get_profile(request.user)
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


class VendorPayoutView(APIView):
    """
    POST /api/v1/vendor/payout/ — save bank / payout account details
    """
    permission_classes = [IsAuthenticated, IsVendor]

    def post(self, request):
        serializer = VendorPayoutDetailsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payout = VendorService.save_payout_details(
            user=request.user,
            data=dict(serializer.validated_data),
        )
        return Response({
            "status": "success",
            "message": "Payout details saved.",
            "data": {
                "bank_name": payout.bank_name,
                "account_name": payout.account_name,
                "account_last4": payout.account_last4,
                "is_verified": payout.is_verified,
            },
        }, status=status.HTTP_201_CREATED)
