# apps/client/apis/sync/profile_views.py
"""
Client Profile API — DRF Sync Views.

URL prefix: /api/v1/client/

Endpoints:
  GET    /api/v1/client/profile/              — fetch my profile
  PATCH  /api/v1/client/profile/              — update profile
  GET    /api/v1/client/addresses/            — list addresses
  POST   /api/v1/client/addresses/            — add address
  DELETE /api/v1/client/addresses/{id}/       — soft-delete address
  POST   /api/v1/client/addresses/{id}/set-default/ — set default
"""
import logging

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.client.selectors.client_selectors import (
    get_client_profile_or_none,
    list_client_addresses,
)
from apps.client.serializers.profile_serializers import (
    AddressCreateSerializer,
    ClientAddressSerializer,
    ClientProfileOutputSerializer,
    ClientProfileUpdateSerializer,
)
from apps.client.services.client_profile_service import ClientProfileService
from apps.common.permissions import IsClient, IsVerifiedUser

logger = logging.getLogger(__name__)


class ClientProfileView(APIView):
    """
    GET  /api/v1/client/profile/ — retrieve profile
    PATCH /api/v1/client/profile/ — update profile
    """
    permission_classes = [IsAuthenticated, IsClient]

    def get(self, request):
        profile = get_client_profile_or_none(request.user)
        if profile is None:
            # Auto-provision and return empty profile
            profile = ClientProfileService.get_profile(request.user)
        serializer = ClientProfileOutputSerializer(profile)
        return Response({
            "status": "success",
            "message": "Profile retrieved successfully.",
            "data": serializer.data,
        })

    def patch(self, request):
        serializer = ClientProfileUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        profile = ClientProfileService.update_profile(
            user=request.user,
            data=serializer.validated_data,
        )
        return Response({
            "status": "success",
            "message": "Profile updated successfully.",
            "data": ClientProfileOutputSerializer(profile).data,
        })


class ClientAddressListCreateView(APIView):
    """
    GET  /api/v1/client/addresses/ — list saved addresses
    POST /api/v1/client/addresses/ — add new address
    """
    permission_classes = [IsAuthenticated, IsClient]

    def get(self, request):
        addresses = list_client_addresses(request.user)
        return Response({
            "status": "success",
            "data": ClientAddressSerializer(addresses, many=True).data,
        })

    def post(self, request):
        serializer = AddressCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        address = ClientProfileService.add_address(
            user=request.user,
            address_data=serializer.validated_data,
        )
        return Response(
            {
                "status": "success",
                "message": "Address added successfully.",
                "data": ClientAddressSerializer(address).data,
            },
            status=status.HTTP_201_CREATED,
        )


class ClientAddressDetailView(APIView):
    """
    DELETE /api/v1/client/addresses/{id}/ — soft-delete address
    """
    permission_classes = [IsAuthenticated, IsClient]

    def delete(self, request, address_id):
        try:
            ClientProfileService.delete_address(
                user=request.user, address_id=address_id
            )
            return Response({
                "status": "success",
                "message": "Address removed.",
            }, status=status.HTTP_200_OK)
        except Exception as e:
            logger.warning(
                "ClientAddressDetailView.delete: not found: %s — %s",
                address_id, e,
            )
            return Response({
                "status": "error",
                "message": "Address not found.",
            }, status=status.HTTP_404_NOT_FOUND)


class ClientAddressSetDefaultView(APIView):
    """
    POST /api/v1/client/addresses/{id}/set-default/
    """
    permission_classes = [IsAuthenticated, IsClient]

    def post(self, request, address_id):
        try:
            address = ClientProfileService.set_default_address(
                user=request.user, address_id=address_id
            )
            return Response({
                "status": "success",
                "message": "Default address updated.",
                "data": ClientAddressSerializer(address).data,
            })
        except Exception as e:
            logger.warning(
                "ClientAddressSetDefaultView: error — %s", e,
            )
            return Response({
                "status": "error",
                "message": "Address not found.",
            }, status=status.HTTP_404_NOT_FOUND)
