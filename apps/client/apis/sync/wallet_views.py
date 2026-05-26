# apps/client/apis/sync/wallet_views.py
"""
Client Wallet API — DRF Sync Views.

Covers wallet balance retrieval, peer-to-peer fund transfers,
and KYC-gated bank withdrawal requests.

URL prefix: /api/v1/client/

Endpoints:
  GET  /api/v1/client/wallet/balance/    — get current wallet balance
  POST /api/v1/client/wallet/transfer/   — P2P fund transfer (PIN protected)
  POST /api/v1/client/wallet/withdraw/   — Bank withdrawal request (KYC + PIN gated)

Design: Write-Sync pattern — all mutations use DRF (Axios) so they
are fully synchronous with DB-transaction guarantees.  Reads are served
by the Ninja async layer.
"""

import logging
from decimal import Decimal, InvalidOperation

from django.contrib.auth import get_user_model
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.renderers import BrowsableAPIRenderer
from rest_framework.views import APIView

from apps.common.permissions import IsClient
from apps.common.renderers import CustomJSONRenderer
from apps.common.responses import error_response, success_response
from apps.wallet.serializers import WalletSerializer, WalletTransferSerializer, WalletWithdrawalSerializer
from apps.wallet.services import WalletBalanceService, WalletProvisioningService, WalletWithdrawalService

User = get_user_model()
logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# BALANCE & PROVISIONING
# ═══════════════════════════════════════════════════════════════════════════════


class ClientWalletBalanceView(generics.RetrieveAPIView):
    """
    GET /api/v1/client/wallet/balance/

    Retrieves the authenticated client's current Fashionistar wallet balance.
    Auto-provisions a wallet via WalletProvisioningService if none exists.

    Security:  IsAuthenticated + IsClient
    Status:    200 OK — balance data returned.
    """

    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]
    serializer_class = WalletSerializer
    permission_classes = [IsAuthenticated, IsClient]

    def get_object(self):
        return WalletProvisioningService.ensure_wallet(self.request.user)


# ═══════════════════════════════════════════════════════════════════════════════
# P2P TRANSFERS
# ═══════════════════════════════════════════════════════════════════════════════


class ClientWalletTransferView(generics.GenericAPIView):
    """
    POST /api/v1/client/wallet/transfer/

    Executes an atomic wallet-to-wallet transfer to another Fashionistar user.

    Body:
      {
        "receiver_id": "<uuid>",
        "amount": "500.00",
        "transaction_password": "1234"
      }

    Security:
      - Verifies the 4-digit Transaction PIN via WalletBalanceService.transfer().
      - KYC gate enforced in the service (sender must be KYC-approved).
      - Idempotency-Key header is forwarded to prevent duplicate transactions.

    Status:
      200 OK: Transfer completed.
      400 Bad Request: Insufficient funds, invalid PIN, or validation error.
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


# ═══════════════════════════════════════════════════════════════════════════════
# BANK WITHDRAWAL REQUESTS
# ═══════════════════════════════════════════════════════════════════════════════


class ClientWalletWithdrawView(APIView):
    """
    POST /api/v1/client/wallet/withdraw/

    Create a KYC-gated, PIN-protected bank withdrawal request.

    This is the correct financial-exit endpoint for the WithdrawalForm UI.
    It uses WalletWithdrawalService.request_withdrawal() which:
      - Asserts the user has an approved KYC submission.
      - Verifies the 4-digit transaction PIN.
      - Moves funds from available_balance → pending_balance (atomic DB txn).
      - Creates an immutable PAYOUT ledger entry (CBN compliance).
      - Writes a compliance audit trail (CBN/GDPR permanent retention).
      - Supports idempotency via Idempotency-Key header.

    Body:
      {
        "amount":         "5000.00",       // min ₦1,000 enforced in Zod (frontend)
        "pin":            "1234",          // 4-digit wallet PIN
        "bank_code":      "057",           // Nigerian bank code (e.g. Zenith = "057")
        "account_number": "0123456789",    // 10-digit NUBAN
        "account_name":   "Jane Doe"       // beneficiary name
      }

    Response (200):
      {
        "transaction_id":    "<uuid>",
        "reference":         "wallet-withdrawal:...",
        "status":            "processing",
        "amount":            "5000.00",
        "available_balance": "15000.00",
        "pending_balance":   "5000.00"
      }

    Error Codes:
      400 — Invalid PIN / insufficient balance / validation errors.
      403 — KYC not approved (assert_kyc_approved gate).
      422 — Idempotent duplicate detected (returns existing transaction).

    Security:
      - IsAuthenticated + IsClient
      - KYC approved (enforced by WalletWithdrawalService)
      - PIN verified (bcrypt check via wallet.verify_pin())
      - Idempotency-Key prevents double-submission on network retry

    CBN Compliance:
      - Funds remain in pending_balance until the payment provider confirms
        the bank transfer (async execution by Celery payout task).
      - The immutable PAYOUT ledger row is created before this response returns.
    """

    permission_classes = [IsAuthenticated, IsClient]
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]

    def post(self, request):
        serializer = WalletWithdrawalSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(
                message="Validation error.",
                data=serializer.errors,
                status=status.HTTP_400_BAD_REQUEST,
            )

        vd = serializer.validated_data
        idempotency_key = request.headers.get("Idempotency-Key", "")

        try:
            result = WalletWithdrawalService.request_withdrawal(
                user=request.user,
                amount=vd["amount"],
                pin=vd["pin"],
                bank_code=vd["bank_code"],
                account_number=vd["account_number"],
                account_name=vd["account_name"],
                idempotency_key=idempotency_key,
            )
        except Exception as exc:
            error_str = str(exc)
            log_level = logger.info if "KYC" in error_str or "PIN" in error_str else logger.warning
            log_level(
                "ClientWalletWithdrawView: withdrawal failed user=%s error=%s",
                getattr(request.user, "email", "?"),
                error_str,
            )
            # Surface the service error directly — the frontend bubbles it to toast.
            return error_response(
                message=error_str,
                status=status.HTTP_400_BAD_REQUEST,
            )

        logger.info(
            "Withdrawal request: ₦%s user=%s txn=%s",
            vd["amount"],
            getattr(request.user, "email", "?"),
            result.get("transaction_id"),
        )
        return success_response(
            data=result,
            message="Withdrawal request submitted. Funds will arrive in 1–3 business days.",
            status=status.HTTP_201_CREATED,
        )


# ═══════════════════════════════════════════════════════════════════════════════
# WALLET TOP-UP INITIATION
# ═══════════════════════════════════════════════════════════════════════════════


class ClientWalletTopUpView(APIView):
    """
    POST /api/v1/client/wallet/topup/initiate/

    Initiates a Paystack wallet top-up payment intent.
    Returns a payment_url the client redirects to for card payment.

    Body:
      {
        "amount": 5000,                          // NGN amount (number)
        "payment_method": "card",                // card | bank_transfer
        "callback_url": "https://.../verify"     // optional redirect URL
      }

    Response (200):
      {
        "status": "pending",
        "payment_url": "https://paystack.com/...",
        "reference": "..."
      }
    """

    permission_classes = [IsAuthenticated, IsClient]
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]

    def post(self, request):
        amount = request.data.get("amount")
        callback_url = request.data.get("callback_url", "")

        try:
            amount_decimal = Decimal(str(amount))
            if amount_decimal <= 0:
                raise ValueError("Amount must be greater than zero.")
        except (InvalidOperation, ValueError, TypeError):
            return error_response(
                message="Invalid amount. Must be a positive number.",
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            from apps.payment.models import PaymentPurpose
            from apps.payment.services import PaymentIntentService
            idempotency_key = (
                request.headers.get("Idempotency-Key")
                or f"wallet-topup:{request.user.pk}:{amount_decimal}"
            )
            intent = PaymentIntentService.initialize_paystack(
                user=request.user,
                amount=amount_decimal,
                purpose=PaymentPurpose.WALLET_TOPUP,
                currency="NGN",
                idempotency_key=idempotency_key,
                metadata={"callback_url": callback_url, "source": "client-dashboard"},
            )
        except Exception as exc:
            logger.warning(
                "ClientWalletTopUpView: failed user=%s amount=%s error=%s",
                getattr(request.user, "email", "?"),
                amount,
                exc,
            )
            return error_response(
                message=str(exc),
                status=status.HTTP_400_BAD_REQUEST,
            )

        return success_response(
            data={
                "status": "pending",
                "payment_url": intent.authorization_url or "",
                "reference": intent.reference,
            },
            message="Top-up payment initialized. Redirect to payment_url to complete.",
            status=status.HTTP_201_CREATED,
        )
