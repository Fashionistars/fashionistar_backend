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
from django.db import transaction
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.permissions import IsClient

User = get_user_model()
logger = logging.getLogger(__name__)


class ClientWalletBalanceView(APIView):
    """
    GET /api/v1/client/wallet/balance/

    Return the authenticated client's current wallet balance.
    Reads from the old userauths.Profile.wallet_balance field.
    Future: move to apps.client.models.ClientProfile.wallet_balance
    when the wallet is fully migrated.
    """
    permission_classes = [IsAuthenticated, IsClient]

    def get(self, request):
        from userauths.models import Profile  # cross-domain read only

        try:
            profile = Profile.objects.get(user=request.user)
        except Profile.DoesNotExist:
            return Response(
                {"status": "error", "message": "Profile not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        return Response({
            "status": "success",
            "data": {"balance": str(profile.wallet_balance)},
        })


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
    Creates Transaction records for both parties.
    Guards: PIN verification, positive amount, sufficient balance.
    """
    permission_classes = [IsAuthenticated, IsClient]

    def post(self, request):
        receiver_id = request.data.get("receiver_id", "").strip()
        raw_amount = request.data.get("amount", "").strip()
        pin = request.data.get("transaction_password", "").strip()

        # ── Input validation ───────────────────────────────────────
        if not receiver_id:
            return Response({"status": "error", "message": "receiver_id is required."}, status=400)
        if not raw_amount:
            return Response({"status": "error", "message": "amount is required."}, status=400)
        if not pin:
            return Response({"status": "error", "message": "transaction_password is required."}, status=400)

        try:
            amount = Decimal(raw_amount)
            if amount <= 0:
                raise ValueError
        except (InvalidOperation, ValueError):
            return Response(
                {"status": "error", "message": "amount must be a positive number."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        from userauths.models import Profile

        # ── Sender checks ─────────────────────────────────────────
        try:
            sender_profile = Profile.objects.get(user=request.user)
        except Profile.DoesNotExist:
            return Response({"status": "error", "message": "Sender profile not found."}, status=404)

        if not sender_profile.check_transaction_password(pin):
            logger.warning("ClientWalletTransferView: invalid PIN for user=%s", request.user.email)
            return Response(
                {"status": "error", "message": "Invalid transaction password."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if sender_profile.wallet_balance < amount:
            return Response({"status": "error", "message": "Insufficient balance."}, status=400)

        # ── Receiver lookup ───────────────────────────────────────
        try:
            receiver = User.objects.get(id=receiver_id)
        except User.DoesNotExist:
            return Response({"status": "error", "message": "Receiver not found."}, status=404)

        try:
            receiver_profile = Profile.objects.get(user=receiver)
        except Profile.DoesNotExist:
            return Response({"status": "error", "message": "Receiver profile not found."}, status=404)

        # ── Atomic transfer ───────────────────────────────────────
        with transaction.atomic():
            try:
                from Paystack_Webhoook_Prod.models import Transaction as TxnModel  # noqa
                TxnModel.objects.create(user=request.user, transaction_type="debit", amount=amount, status="success")
                TxnModel.objects.create(user=receiver, transaction_type="credit", amount=amount, status="success")
            except Exception as exc:
                logger.warning("ClientWalletTransferView: txn record failed (non-fatal): %s", exc)

            sender_profile.wallet_balance -= amount
            sender_profile.save(update_fields=["wallet_balance"])
            receiver_profile.wallet_balance += amount
            receiver_profile.save(update_fields=["wallet_balance"])

        logger.info(
            "Transfer: ₦%s from user=%s to user=%s",
            amount, request.user.email, receiver.email,
        )
        return Response({
            "status": "success",
            "message": "Transfer successful.",
            "data": {
                "sender_balance": str(sender_profile.wallet_balance),
                "receiver_balance": str(receiver_profile.wallet_balance),
            },
        })
