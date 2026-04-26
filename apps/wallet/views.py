# apps/wallet/views.py
"""
Financial Module — Digital Wallet & Escrow Views
================================================

Handles user wallet management, transaction PIN security, and the Escrow
system for client-vendor transactions.

Flow:
  1. Provisioning (Wallet created on first access via MyWalletView)
  2. Security (PIN set/verify/change for transaction authorization)
  3. Escrow (Hold funds during order creation, Release on completion, or Refund on dispute)
"""

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.renderers import BrowsableAPIRenderer

from apps.common.renderers import CustomJSONRenderer
from apps.common.responses import success_response, error_response
from apps.wallet.models import Wallet
from apps.wallet.serializers import (
    EscrowHoldSerializer,
    EscrowRefundSerializer,
    EscrowReleaseResponseSerializer,
    EscrowReleaseSerializer,
    WalletHoldSerializer,
    WalletPinChangeSerializer,
    WalletPinSetSerializer,
    WalletPinVerifyResponseSerializer,
    WalletPinVerifySerializer,
    WalletSerializer,
)
from apps.wallet.services import EscrowService, WalletPinService, WalletProvisioningService

User = get_user_model()


def _idempotency_key(request) -> str:
    """Helper to extract idempotency key from headers."""
    return request.headers.get("Idempotency-Key", "")


# ===========================================================================
# GET /api/v1/wallet/me/
# ===========================================================================


class MyWalletView(generics.GenericAPIView):
    """
    Retrieves the authenticated user's digital wallet profile.

    Flow:
      1. Check if wallet exists for the user.
      2. If not, provision a new wallet with zero balance.
      3. Return balance and hold statistics.

    Status Codes:
      200 OK: Returns wallet details.
    """
    permission_classes = [IsAuthenticated]
    serializer_class = WalletSerializer
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]

    def get(self, request):
        wallet = WalletProvisioningService.ensure_wallet(request.user)
        return success_response(
            data=self.get_serializer(wallet).data,
            message="Wallet retrieved successfully.",
        )


# ===========================================================================
# GET /api/v1/wallet/balance/
# ===========================================================================


class WalletBalanceView(MyWalletView):
    """
    Alias for MyWalletView, specifically focusing on the current balance state.

    Legacy Context:
      Previously served as a simple balance-only endpoint.
    """
    pass


# ===========================================================================
# PIN SECURITY OPERATIONS
# ===========================================================================


class WalletSetPinView(generics.GenericAPIView):
    """
    Establishes a 4-digit transaction PIN for wallet authorization.

    Flow:
      1. User provides a 4-digit numeric string.
      2. Service hashes the PIN for secure storage.
      3. Enables transaction capabilities for the wallet.

    Status Codes:
      200 OK: PIN established.
      400 Bad Request: Invalid format or PIN already set.
    """
    permission_classes = [IsAuthenticated]
    serializer_class = WalletPinSetSerializer
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            wallet = WalletPinService.set_pin(request.user, serializer.validated_data["pin"])
            return success_response(
                data=WalletSerializer(wallet).data,
                message="Transaction PIN set successfully.",
            )
        except ValidationError as exc:
            return error_response(message=str(exc), status=status.HTTP_400_BAD_REQUEST)


class WalletVerifyPinView(generics.GenericAPIView):
    """
    Validates a transaction PIN without performing a financial operation.

    Use Case:
      Frontend checks PIN before showing "Confirm Transfer" buttons.

    Status Codes:
      200 OK: returns {"valid": bool}
    """
    permission_classes = [IsAuthenticated]
    serializer_class = WalletPinVerifySerializer
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        valid = WalletPinService.verify_pin(request.user, serializer.validated_data["pin"])
        return success_response(
            data={"valid": valid},
            message="PIN verification complete.",
        )


class WalletChangePinView(generics.GenericAPIView):
    """
    Updates an existing transaction PIN after verifying the current one.

    Security:
      Requires 'current_pin' to prevent unauthorized changes.

    Status Codes:
      200 OK: PIN updated.
      400 Bad Request: Invalid current PIN or weak new PIN.
    """
    permission_classes = [IsAuthenticated]
    serializer_class = WalletPinChangeSerializer
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            wallet = WalletPinService.change_pin(
                request.user,
                serializer.validated_data["current_pin"],
                serializer.validated_data["new_pin"],
            )
        except ValidationError as exc:
            return error_response(message=str(exc), status=status.HTTP_400_BAD_REQUEST)

        return success_response(
            data=WalletSerializer(wallet).data,
            message="Transaction PIN changed successfully.",
        )


# ===========================================================================
# ESCROW SYSTEM OPERATIONS
# ===========================================================================


class EscrowHoldView(generics.GenericAPIView):
    """
    Places funds on escrow hold when a new order is initialized.

    Flow:
      1. Verify user has sufficient balance.
      2. Deduct amount from available balance.
      3. Create a Hold record with PENDING status.
      4. Increment 'held_balance'.

    Status Codes:
      201 Created: Funds successfully locked in escrow.
      400 Bad Request: Insufficient balance.
    """
    permission_classes = [IsAuthenticated]
    serializer_class = EscrowHoldSerializer
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            hold = EscrowService.hold_order_payment(
                client_user=request.user,
                idempotency_key=_idempotency_key(request),
                **serializer.validated_data,
            )
        except ValidationError as exc:
            return error_response(message=str(exc), status=status.HTTP_400_BAD_REQUEST)

        return success_response(
            data=WalletHoldSerializer(hold).data,
            message="Payment placed on escrow hold.",
            status=status.HTTP_201_CREATED,
        )


class EscrowReleaseView(generics.GenericAPIView):
    """
    Releases escrowed funds to the vendor after order completion.

    Flow:
      1. Locate the Hold record by reference.
      2. Verify client authorization (or automated release trigger).
      3. Calculate and deduct platform commission.
      4. Credit vendor's available balance.
      5. Mark Hold as RELEASED.

    Status Codes:
      200 OK: Vendor successfully credited.
    """
    permission_classes = [IsAuthenticated]
    serializer_class = EscrowReleaseSerializer
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            vendor_user = User.objects.get(pk=serializer.validated_data["vendor_user_id"])
            result = EscrowService.release_order_payment(
                hold_reference=serializer.validated_data["hold_reference"],
                vendor_user=vendor_user,
                commission_rate=serializer.validated_data["commission_rate"],
                idempotency_key=_idempotency_key(request),
            )
            return success_response(
                data=result,
                message="Escrow funds released successfully.",
            )
        except User.DoesNotExist:
            return error_response(message="Target vendor user not found.", status=status.HTTP_404_NOT_FOUND)
        except ValidationError as exc:
            return error_response(message=str(exc), status=status.HTTP_400_BAD_REQUEST)


class EscrowRefundView(generics.GenericAPIView):
    """
    Refunds escrowed funds back to the client available balance.

    Use Case:
      Order cancellation or dispute resolution in favor of the client.

    Flow:
      1. Move funds from held_balance back to available_balance.
      2. Mark Hold as REFUNDED.

    Status Codes:
      200 OK: Client successfully refunded.
    """
    permission_classes = [IsAuthenticated]
    serializer_class = EscrowRefundSerializer
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            hold = EscrowService.refund_escrow(
                hold_reference=serializer.validated_data["hold_reference"],
                idempotency_key=_idempotency_key(request),
            )
            return success_response(
                data=WalletHoldSerializer(hold).data,
                message="Escrow funds refunded successfully.",
            )
        except ValidationError as exc:
            return error_response(message=str(exc), status=status.HTTP_400_BAD_REQUEST)
