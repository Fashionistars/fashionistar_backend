# apps/client/apis/sync/wallet_views.py
"""
Client Wallet API — DRF Sync Views.

Migrated & modernized from legacy customer/wallet_balance.py.
Covers wallet balance retrieval and peer-to-peer fund transfers.

URL prefix: /api/v1/client/

Endpoints:
  GET  /api/v1/client/wallet/balance/   — get current wallet balance
  POST /api/v1/client/wallet/transfer/  — transfer funds to another user (PIN protected)
"""
import logging
from decimal import Decimal, InvalidOperation

from django.contrib.auth import get_user_model
from rest_framework.views import APIView
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.common.permissions import IsClient
from apps.wallet.serializers import WalletSerializer
from apps.wallet.services import WalletBalanceService, WalletProvisioningService

User = get_user_model()
logger = logging.getLogger(__name__)


class ClientWalletBalanceView(APIView):
    """
    GET /api/v1/client/wallet/balance/

    Return the authenticated client's current Fashionistar wallet balance.
    """

    permission_classes = [IsAuthenticated, IsClient]

    def get(self, request):
        wallet = WalletProvisioningService.ensure_wallet(request.user)
        return Response(
            {
                "status": "success",
                "data": WalletSerializer(wallet).data,
            }
        )


class ClientWalletTransferView(APIView):
    """
    POST /api/v1/client/wallet/transfer/

    Body:
      {
        "receiver_id": "<uuid>",
        "amount": "500.00",
        "transaction_password": "1234"
      }

    Atomically deduct from sender, credit receiver.
    Creates a Fashionistar ledger entry.
    Guards: PIN verification, positive amount, sufficient balance.
    """

    permission_classes = [IsAuthenticated, IsClient]

    def post(self, request):
        receiver_id = request.data.get("receiver_id", "").strip()
        raw_amount = request.data.get("amount", "").strip()
        pin = request.data.get("transaction_password", "").strip()

        # ── Input validation ───────────────────────────────────────
        if not receiver_id:
            return Response(
                {"status": "error", "message": "receiver_id is required."}, status=400
            )
        if not raw_amount:
            return Response(
                {"status": "error", "message": "amount is required."}, status=400
            )
        if not pin:
            return Response(
                {"status": "error", "message": "transaction_password is required."},
                status=400,
            )

        try:
            amount = Decimal(raw_amount)
            if amount <= 0:
                raise ValueError
        except (InvalidOperation, ValueError):
            return Response(
                {"status": "error", "message": "amount must be a positive number."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ── Receiver lookup ───────────────────────────────────────
        try:
            receiver = User.objects.get(id=receiver_id)
        except User.DoesNotExist:
            return Response(
                {"status": "error", "message": "Receiver not found."}, status=404
            )

        try:
            result = WalletBalanceService.transfer(
                sender_user=request.user,
                receiver_user=receiver,
                amount=amount,
                pin=pin,
                idempotency_key=request.headers.get("Idempotency-Key", ""),
            )
        except Exception as exc:
            logger.warning(
                "ClientWalletTransferView: transfer failed user=%s error=%s",
                request.user.pk,
                exc,
            )
            return Response(
                {"status": "error", "message": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        logger.info(
            "Transfer: ₦%s from user=%s to user=%s",
            amount,
            request.user.email,
            receiver.email,
        )
        return Response(
            {
                "status": "success",
                "message": "Transfer successful.",
                "data": result,
            }
        )


# apps/client/apis/sync/wallet_views.py
"""
Client Wallet API — DRF Sync Views
==================================

Provides secure access to the internal Fashionistar wallet system.
Handles balance inquiries and peer-to-peer fund transfers.

URL prefix: /api/v1/client/wallet/

Security:
  - Transfers are guarded by a 4-digit Transaction PIN.
  - Idempotency-Key header is enforced to prevent duplicate transactions.
"""

import logging
from django.contrib.auth import get_user_model
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.renderers import BrowsableAPIRenderer

from apps.common.permissions import IsClient
from apps.common.renderers import CustomJSONRenderer
from apps.common.responses import error_response, success_response
from apps.wallet.serializers import WalletSerializer, WalletTransferSerializer
from apps.wallet.services import WalletBalanceService, WalletProvisioningService

User = get_user_model()
logger = logging.getLogger(__name__)


# ===========================================================================
# BALANCE & PROVISIONING
# ===========================================================================


class ClientWalletBalanceView(generics.RetrieveAPIView):
    """
    Retrieves the current balance for the authenticated client.

    Validation Logic:
      - Automatically provisions a wallet via WalletProvisioningService if none exists.

    Security:
      - Requires IsAuthenticated + IsClient.

    Status Codes:
      200 OK: Balance data returned.
    """

    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]
    serializer_class = WalletSerializer
    permission_classes = [IsAuthenticated, IsClient]

    def get_object(self):
        return WalletProvisioningService.ensure_wallet(self.request.user)


# ===========================================================================
# P2P TRANSFERS
# ===========================================================================


class ClientWalletTransferView(generics.GenericAPIView):
    """
    Executes a fund transfer to another Fashionistar user.

    Validation Logic:
      - Validates receiver existence and active status.
      - Enforces minimum transfer amount (₦100).
      - Checks for sufficient balance before initiation.

    Security:
      - Verifies the 4-digit Transaction PIN.
      - Uses Idempotency-Key to ensure exactly-once delivery.

    Status Codes:
      200 OK: Transfer completed.
      400 Bad Request: Insufficient funds or invalid data.
      404 Not Found: Receiver not found.
    """

    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]
    permission_classes = [IsAuthenticated, IsClient]
    serializer_class = WalletTransferSerializer

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        receiver_id = serializer.validated_data["receiver_id"]
        amount = serializer.validated_data["amount"]
        pin = serializer.validated_data["transaction_password"]

        try:
            receiver = User.objects.get(id=receiver_id)
        except (User.DoesNotExist, ValueError):
            return error_response(
                message="Receiver not found.", status=status.HTTP_404_NOT_FOUND
            )

        try:
            result = WalletBalanceService.transfer(
                sender_user=request.user,
                receiver_user=receiver,
                amount=amount,
                pin=pin,
                idempotency_key=request.headers.get("Idempotency-Key", ""),
            )
        except Exception as exc:
            logger.warning(
                "ClientWalletTransferView: transfer failed user=%s error=%s",
                request.user.email,
                exc,
            )
            return error_response(message=str(exc), status=status.HTTP_400_BAD_REQUEST)

        logger.info(
            "Transfer: ₦%s from user=%s to user=%s",
            amount,
            request.user.email,
            receiver.email,
        )
        return success_response(
            data=result,
            message="Transfer successful.",
        )
