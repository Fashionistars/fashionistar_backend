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

from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

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
from apps.common.renderers import CustomJSONRenderer, error_response, success_response

logger = logging.getLogger(__name__)


class ClientProfileView(generics.RetrieveUpdateAPIView):
    """
    GET  /api/v1/client/profile/ — retrieve profile
    PATCH /api/v1/client/profile/ — update profile
    """

    renderer_classes = [CustomJSONRenderer]
    permission_classes = [IsAuthenticated, IsClient]

    def get_object(self):
        profile = get_client_profile_or_none(self.request.user)
        if profile is None:
            # Auto-provision if missing
            profile = ClientProfileService.get_profile(self.request.user)
        return profile

    def get_serializer_class(self):
        if self.request.method in ["PATCH", "PUT"]:
            return ClientProfileUpdateSerializer
        return ClientProfileOutputSerializer

    def update(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        profile = ClientProfileService.update_profile(
            user=request.user,
            data=serializer.validated_data,
        )
        return success_response(
            data=ClientProfileOutputSerializer(profile).data,
            message="Profile updated successfully.",
        )


class ClientAddressListCreateView(generics.ListCreateAPIView):
    """
    GET  /api/v1/client/addresses/ — list saved addresses
    POST /api/v1/client/addresses/ — add new address
    """

    renderer_classes = [CustomJSONRenderer]
    permission_classes = [IsAuthenticated, IsClient]

    def get_serializer_class(self):
        if self.request.method == "POST":
            return AddressCreateSerializer
        return ClientAddressSerializer

    def get_queryset(self):
        return list_client_addresses(self.request.user)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        address = ClientProfileService.add_address(
            user=request.user,
            address_data=serializer.validated_data,
        )
        return success_response(
            data=ClientAddressSerializer(address).data,
            message="Address added successfully.",
            status=status.HTTP_201_CREATED,
        )


class ClientAddressDetailView(generics.DestroyAPIView):
    """
    DELETE /api/v1/client/addresses/{id}/ — soft-delete address
    """

    renderer_classes = [CustomJSONRenderer]
    permission_classes = [IsAuthenticated, IsClient]
    lookup_url_kwarg = "address_id"

    def destroy(self, request, *args, **kwargs):
        address_id = self.kwargs.get(self.lookup_url_kwarg)
        try:
            ClientProfileService.delete_address(
                user=request.user, address_id=address_id
            )
            return success_response(message="Address removed.")
        except Exception as e:
            logger.warning(
                "ClientAddressDetailView.delete: not found: %s — %s",
                address_id,
                e,
            )
            return error_response(
                message="Address not found.",
                status=status.HTTP_404_NOT_FOUND,
            )


class ClientAddressSetDefaultView(generics.GenericAPIView):
    """
    POST /api/v1/client/addresses/{id}/set-default/
    Set a specific address as the default shipping address.
    """

    renderer_classes = [CustomJSONRenderer]
    permission_classes = [IsAuthenticated, IsClient]
    serializer_class = ClientAddressSerializer
    lookup_url_kwarg = "address_id"

    def post(self, request, address_id):
        try:
            address = ClientProfileService.set_default_address(
                user=request.user, address_id=address_id
            )
            return success_response(
                data=ClientAddressSerializer(address).data,
                message="Default address updated.",
            )
        except Exception as e:
            logger.warning(
                "ClientAddressSetDefaultView: error — %s",
                e,
            )
            return error_response(
                message="Address not found.",
                status=status.HTTP_404_NOT_FOUND,
            )
