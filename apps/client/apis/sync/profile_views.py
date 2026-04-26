# apps/client/apis/sync/profile_views.py
"""
Client Profile API — DRF Sync Views
===================================

Handles client identity, measurement profiles, and address management.
Provides secure storage for shipping addresses and personalized data.

URL prefix: /api/v1/client/

Design Principles:
  - Auto-Provisioning: Transparently creates a Client profile if missing upon first access.
  - Multi-Tenancy: Strictly filters addresses by the authenticated user's ownership.
"""

from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.renderers import BrowsableAPIRenderer

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
from apps.common.permissions import IsClient
from apps.common.renderers import CustomJSONRenderer
from apps.common.responses import success_response, error_response


# ===========================================================================
# PROFILE MANAGEMENT
# ===========================================================================


class ClientProfileView(generics.RetrieveUpdateAPIView):
    """
    Retrieves or updates the client's personal profile.

    Validation Logic:
      - PATCH: Validates name, phone, and optional bio/avatar.
      - Provisioning: Automatically calls ClientProfileService.get_profile if missing.

    Security:
      - Requires IsAuthenticated + IsClient.

    Status Codes:
      200 OK: Data returned/updated.
    """
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]
    permission_classes = [IsAuthenticated, IsClient]

    def get_object(self):
        profile = get_client_profile_or_none(self.request.user)
        if profile is None:
            profile = ClientProfileService.get_profile(self.request.user)
        return profile

    def get_serializer_class(self):
        if self.request.method in ['PATCH', 'PUT']:
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


# ===========================================================================
# ADDRESS BOOK
# ===========================================================================


class ClientAddressListCreateView(generics.ListCreateAPIView):
    """
    Manages the collection of shipping addresses for the client.

    Validation Logic:
      - POST: Validates street, city, state, and zip code.
      - Scoping: get_queryset ensures only the user's addresses are listed.

    Status Codes:
      200 OK: List returned.
      201 Created: New address saved.
    """
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]
    permission_classes = [IsAuthenticated, IsClient]

    def get_serializer_class(self):
        if self.request.method == 'POST':
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
    Soft-deletes a specific shipping address.

    Validation Logic:
      - Verifies address ownership before deletion.

    Status Codes:
      200 OK: Address removed.
      404 Not Found: Address missing or unauthorized.
    """
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]
    permission_classes = [IsAuthenticated, IsClient]
    lookup_url_kwarg = 'address_id'

    def destroy(self, request, *args, **kwargs):
        address_id = self.kwargs.get(self.lookup_url_kwarg)
        try:
            ClientProfileService.delete_address(
                user=request.user, address_id=address_id
            )
            return success_response(message="Address removed.")
        except Exception:
            return error_response(
                message="Address not found.",
                status=status.HTTP_404_NOT_FOUND,
            )


class ClientAddressSetDefaultView(generics.GenericAPIView):
    """
    Sets a specific address as the primary shipping destination.

    Flow:
      - Updates all other addresses to default=False.
      - Sets target address to default=True.

    Status Codes:
      200 OK: Default updated.
      404 Not Found: Address missing.
    """
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]
    permission_classes = [IsAuthenticated, IsClient]
    serializer_class = ClientAddressSerializer
    lookup_url_kwarg = 'address_id'

    def post(self, request, address_id):
        try:
            address = ClientProfileService.set_default_address(
                user=request.user, address_id=address_id
            )
            return success_response(
                data=ClientAddressSerializer(address).data,
                message="Default address updated.",
            )
        except Exception:
            return error_response(
                message="Address not found.",
                status=status.HTTP_404_NOT_FOUND,
            )
