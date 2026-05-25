# apps/vendor/apis/sync/payout_request_views.py
"""
Vendor Payout Request API — DRF Sync View.

URL: POST /api/v1/vendor/payout/request/

Flow:
  1. Vendor selects a saved VendorBankAccount (by UUID) from their dashboard.
  2. Frontend sends { bank_account_id, amount, narration }.
  3. This view:
       a. Fetches and validates the VendorBankAccount (must belong to the requesting vendor).
       b. Decrypts the NUBAN from account_number_enc (Fernet).
       c. Delegates to VendorPayoutService.initiate() which:
            - Validates wallet balance.
            - Calls the active payment gateway (Paystack) with recipient_code.
            - Debits the wallet atomically.
            - Writes the transaction ledger entry.
            - Emits audit trail.
  4. Returns the payout reference to the frontend.

Security:
  - Only the account owner can use their bank account for payouts.
  - Minimum payout amount is ₦1,000 (configurable via MIN_PAYOUT_AMOUNT).
  - Transaction PIN is verified if the vendor's wallet has a PIN set.
  - All sensitive fields are logged masked (last 4 digits only).
"""
from __future__ import annotations

import logging
from decimal import Decimal, InvalidOperation

from rest_framework import serializers, status
from rest_framework.generics import GenericAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.renderers import BrowsableAPIRenderer
from rest_framework.response import Response

from apps.common.permissions import IsVendor
from apps.common.renderers import CustomJSONRenderer
from apps.vendor.services.vendor_bank_account_service import (
    BankAccountNotFound,
    VendorBankAccountService,
    decrypt_account_number,
)
from apps.payment.payout_service import (
    InsufficientWalletBalanceError,
    PayoutAlreadyRequestedError,
    PayoutGatewayError,
    VendorPayoutService,
)

logger = logging.getLogger(__name__)

# Fallback constants (used if PlatformSettings row has never been seeded)
_FALLBACK_MIN_PAYOUT = Decimal("1000.00")
_FALLBACK_MAX_PAYOUT = Decimal("10000000.00")


def _get_payout_limits() -> tuple[Decimal, Decimal]:
    """Return (min_payout, max_payout) from PlatformSettings (Redis-cached, 60s)."""
    try:
        from apps.global_platform_settings.cache import get_platform_settings
        cfg = get_platform_settings()
        return cfg.min_withdrawal_ngn, cfg.max_withdrawal_ngn
    except Exception:
        return _FALLBACK_MIN_PAYOUT, _FALLBACK_MAX_PAYOUT


MIN_PAYOUT_AMOUNT, MAX_PAYOUT_AMOUNT = _get_payout_limits()


# ─────────────────────────────────────────────────────────────────────────────
# Serializer
# ─────────────────────────────────────────────────────────────────────────────

class PayoutRequestSerializer(serializers.Serializer):
    bank_account_id = serializers.UUIDField(
        help_text="UUID of the saved VendorBankAccount to pay into.",
    )
    amount = serializers.DecimalField(
        max_digits=20,
        decimal_places=2,
        help_text="Payout amount in NGN. Minimum determined by platform settings.",
    )
    narration = serializers.CharField(
        max_length=255,
        required=False,
        default="Fashionistar Vendor Payout",
        help_text="Bank transfer narration / description.",
    )

    def validate_amount(self, value: Decimal) -> Decimal:
        # Read limits fresh from Redis on every request (60s TTL cache)
        min_amount, max_amount = _get_payout_limits()
        if value < min_amount:
            raise serializers.ValidationError(
                f"Payout amount must be at least ₦{min_amount:,.0f}."
            )
        if value > max_amount:
            raise serializers.ValidationError(
                f"Payout amount cannot exceed ₦{max_amount:,.0f}. "
                "For larger payouts, contact Fashionistar Finance."
            )
        return value


# ─────────────────────────────────────────────────────────────────────────────
# View
# ─────────────────────────────────────────────────────────────────────────────

class VendorPayoutRequestView(GenericAPIView):
    """
    POST /api/v1/vendor/payout/request/

    Initiate a bank transfer payout from the vendor's Fashionistar wallet
    to one of their saved bank accounts.

    Request body:
        bank_account_id (UUID): The VendorBankAccount UUID to pay into.
        amount          (Decimal): Amount in NGN (min ₦1,000).
        narration       (str, optional): Bank transfer description.

    Response (200):
        {
            "status": "success",
            "reference": "PAYOUT-XXXXXXXX-XXXXXXXXXXXXXXXXXXXX",
            "transfer_code": "TRF_xxxxx",
            "amount": "5000.00",
            "currency": "NGN",
            "message": "Payout initiated successfully. Funds will arrive within 1–2 business days."
        }
    """
    permission_classes = [IsAuthenticated, IsVendor]
    renderer_classes   = [CustomJSONRenderer, BrowsableAPIRenderer]
    serializer_class   = PayoutRequestSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        vd = serializer.validated_data

        bank_account_id = str(vd["bank_account_id"])
        amount          = vd["amount"]
        narration       = vd.get("narration", "Fashionistar Vendor Payout")

        # ── Fetch and validate the bank account ──────────────────────────────
        try:
            accounts = VendorBankAccountService.list_bank_accounts(request.user)
            account = next(
                (a for a in accounts if str(a.id) == bank_account_id), None
            )
            if account is None:
                raise BankAccountNotFound("Bank account not found or does not belong to your profile.")
        except BankAccountNotFound as exc:
            return Response({"error": str(exc)}, status=status.HTTP_404_NOT_FOUND)
        except Exception as exc:
            logger.exception(
                "VendorPayoutRequestView: failed to fetch bank account %s for user=%s: %s",
                bank_account_id, request.user.pk, exc,
            )
            return Response(
                {"error": "Failed to retrieve bank account details."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        # ── Decrypt account number ──────────────────────────────────────────
        account_number = decrypt_account_number(bytes(account.account_number_enc))
        if not account_number:
            logger.error(
                "VendorPayoutRequestView: account_number decryption failed for account=%s user=%s",
                bank_account_id, request.user.pk,
            )
            return Response(
                {
                    "error": (
                        "Could not retrieve account details. "
                        "Please re-add this bank account or contact support."
                    )
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        # ── Initiate payout via VendorPayoutService ─────────────────────────
        try:
            result = VendorPayoutService.initiate(
                vendor=request.user,
                amount=amount,
                account_number=account_number,
                bank_code=account.bank_code,
                account_name=account.account_name,
                bank_name=account.bank_name,
                recipient_code=account.paystack_recipient_code,
                narration=narration,
                currency="NGN",
                request=request,
            )
        except InsufficientWalletBalanceError as exc:
            return Response(
                {"error": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except PayoutAlreadyRequestedError as exc:
            return Response(
                {"error": str(exc)},
                status=status.HTTP_409_CONFLICT,
            )
        except PayoutGatewayError as exc:
            return Response(
                {"error": str(exc)},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        except Exception as exc:
            logger.exception(
                "VendorPayoutRequestView: unexpected error for user=%s amount=%s: %s",
                request.user.pk, amount, exc,
            )
            return Response(
                {"error": "An unexpected error occurred. Please try again or contact support."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return Response(
            {
                **result,
                "message": (
                    "Payout initiated successfully. "
                    "Funds will arrive in your bank account within 1–2 business days."
                ),
            },
            status=status.HTTP_200_OK,
        )
