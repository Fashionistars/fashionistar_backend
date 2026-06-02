# apps/vendor/apis/sync/bank_account_views.py
"""
Vendor Bank Account API — DRF Sync Views.

URL prefix: /api/v1/vendor/

Endpoints:
  POST   /api/v1/vendor/bank-accounts/resolve/      — resolve account name via Paystack
  GET    /api/v1/vendor/bank-accounts/               — list saved bank accounts (max 5)
  POST   /api/v1/vendor/bank-accounts/               — create and register bank account
  DELETE /api/v1/vendor/bank-accounts/<uuid:pk>/     — delete a saved bank account
  PATCH  /api/v1/vendor/bank-accounts/<uuid:pk>/default/ — set as default account
"""
from __future__ import annotations

import logging

from rest_framework import serializers, status
from rest_framework.generics import GenericAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.renderers import BrowsableAPIRenderer
from rest_framework.response import Response

from apps.common.permissions import IsVendor
from apps.common.renderers import CustomJSONRenderer
from apps.vendor.models import VendorBankAccount
from apps.vendor.services.vendor_bank_account_service import (
    BankAccountLimitExceeded,
    BankAccountNotFound,
    DuplicateBankAccount,
    PaystackRecipientError,
    VendorBankAccountService,
)

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Serializers (inline — simple enough not to warrant a separate file)
# ─────────────────────────────────────────────────────────────────────────────

class BankAccountResolveSerializer(serializers.Serializer):
    account_number = serializers.RegexField(
        regex=r"^\d{10}$",
        error_messages={
            "invalid": "Account number must be exactly 10 digits.",
        },
    )
    bank_code = serializers.RegexField(
        regex=r"^\d{3,10}$",
        error_messages={
            "invalid": "Bank code must be 3–10 digits.",
        },
    )


class BankAccountCreateSerializer(serializers.Serializer):
    account_number = serializers.RegexField(
        regex=r"^\d{10}$",
        error_messages={
            "invalid": "Account number must be exactly 10 digits.",
        },
    )
    bank_code = serializers.CharField(max_length=10)
    bank_name = serializers.CharField(max_length=150)
    account_name = serializers.CharField(
        max_length=200,
        help_text="Account holder name as resolved by Paystack.",
    )

    def validate_bank_name(self, value: str) -> str:
        if not value.strip():
            raise serializers.ValidationError("Bank name is required.")
        return value.strip()

    def validate_account_name(self, value: str) -> str:
        if not value.strip():
            raise serializers.ValidationError("Account name is required.")
        return value.strip()


class BankAccountOutputSerializer(serializers.Serializer):
    """Safe serializer — never returns full account_number or enc bytes."""
    id                      = serializers.UUIDField()
    bank_name               = serializers.CharField()
    bank_code               = serializers.CharField()
    account_name            = serializers.CharField()
    account_last4           = serializers.CharField()
    masked_account          = serializers.CharField()
    paystack_recipient_code = serializers.CharField()
    kyc_name_matched        = serializers.BooleanField()
    is_default              = serializers.BooleanField()
    verification_status     = serializers.CharField()
    is_verified             = serializers.BooleanField()
    created_at              = serializers.DateTimeField()

    def to_representation(self, instance) -> dict:
        return {
            "id":                      str(instance.id),
            "bank_name":               instance.bank_name,
            "bank_code":               instance.bank_code,
            "account_name":            instance.account_name,
            "account_last4":           instance.account_last4,
            "masked_account":          instance.masked_account,
            "paystack_recipient_code": instance.paystack_recipient_code,
            "kyc_name_matched":        instance.kyc_name_matched,
            "is_default":              instance.is_default,
            "verification_status":     instance.verification_status,
            "is_verified":             instance.is_verified,
            "created_at":              instance.created_at.isoformat(),
        }


# ─────────────────────────────────────────────────────────────────────────────
# Views
# ─────────────────────────────────────────────────────────────────────────────

class VendorBankAccountResolveView(GenericAPIView):
    """
    POST /api/v1/vendor/bank-accounts/resolve/

    Proxy Paystack /bank/resolve to retrieve the account holder name.
    This endpoint is called by the frontend "Resolve Name" button in the
    Add Bank Account modal.

    Request body:
        account_number (str): 10-digit NUBAN
        bank_code      (str): Paystack bank code (e.g. "044")

    Response (200):
        { account_name: str, account_number: str }
    """
    permission_classes = [IsAuthenticated, IsVendor]
    renderer_classes   = [CustomJSONRenderer, BrowsableAPIRenderer]
    serializer_class   = BankAccountResolveSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            result = VendorBankAccountService.resolve_account(
                account_number=serializer.validated_data["account_number"],
                bank_code=serializer.validated_data["bank_code"],
            )
        except PaystackRecipientError as exc:
            return Response(
                {"error": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as exc:
            logger.exception(
                "VendorBankAccountResolveView: unexpected error for user=%s: %s",
                request.user.pk, exc,
            )
            return Response(
                {"error": "An unexpected error occurred. Please try again."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return Response({"data": result}, status=status.HTTP_200_OK)


class VendorBankAccountListCreateView(GenericAPIView):
    """
    GET  /api/v1/vendor/bank-accounts/ — list saved bank accounts
    POST /api/v1/vendor/bank-accounts/ — create a new bank account
    """
    permission_classes = [IsAuthenticated, IsVendor]
    renderer_classes   = [CustomJSONRenderer, BrowsableAPIRenderer]

    def get_serializer_class(self):
        if self.request.method == "POST":
            return BankAccountCreateSerializer
        return BankAccountOutputSerializer

    def get(self, request, *args, **kwargs):
        accounts = VendorBankAccountService.list_bank_accounts(request.user)
        data = [
            BankAccountOutputSerializer().to_representation(acct)
            for acct in accounts
        ]
        return Response({"data": data, "count": len(data)}, status=status.HTTP_200_OK)

    def post(self, request, *args, **kwargs):
        serializer = BankAccountCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        vd = serializer.validated_data

        try:
            account = VendorBankAccountService.create_bank_account(
                user=request.user,
                account_number=vd["account_number"],
                bank_code=vd["bank_code"],
                account_name=vd["account_name"],
                bank_name=vd["bank_name"],
            )
        except BankAccountLimitExceeded as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except DuplicateBankAccount as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except PaystackRecipientError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as exc:
            logger.exception(
                "VendorBankAccountListCreateView.post: error for user=%s: %s",
                request.user.pk, exc,
            )
            return Response(
                {"error": "An unexpected error occurred while saving bank account."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        output = BankAccountOutputSerializer().to_representation(account)
        return Response(
            {"message": "Bank account saved successfully.", "data": output},
            status=status.HTTP_201_CREATED,
        )


class VendorBankAccountDeleteView(GenericAPIView):
    """
    DELETE /api/v1/vendor/bank-accounts/<uuid:pk>/
    Soft-delete the bank account and clean up the Paystack recipient.
    """
    permission_classes = [IsAuthenticated, IsVendor]
    renderer_classes   = [CustomJSONRenderer, BrowsableAPIRenderer]
    queryset           = VendorBankAccount.objects.none()

    def delete(self, request, pk: str, *args, **kwargs):
        try:
            VendorBankAccountService.delete_bank_account(
                user=request.user,
                account_id=str(pk),
            )
        except BankAccountNotFound as exc:
            return Response({"error": str(exc)}, status=status.HTTP_404_NOT_FOUND)
        except PaystackRecipientError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as exc:
            logger.exception(
                "VendorBankAccountDeleteView: error for user=%s pk=%s: %s",
                request.user.pk, pk, exc,
            )
            return Response(
                {"error": "An unexpected error occurred."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return Response(status=status.HTTP_204_NO_CONTENT)


class VendorBankAccountSetDefaultView(GenericAPIView):
    """
    PATCH /api/v1/vendor/bank-accounts/<uuid:pk>/default/
    Set the specified bank account as the vendor's default payout account.
    """
    permission_classes = [IsAuthenticated, IsVendor]
    renderer_classes   = [CustomJSONRenderer, BrowsableAPIRenderer]
    queryset           = VendorBankAccount.objects.none()

    def patch(self, request, pk: str, *args, **kwargs):
        try:
            account = VendorBankAccountService.set_default_account(
                user=request.user,
                account_id=str(pk),
            )
        except BankAccountNotFound as exc:
            return Response({"error": str(exc)}, status=status.HTTP_404_NOT_FOUND)
        except Exception as exc:
            logger.exception(
                "VendorBankAccountSetDefaultView: error for user=%s pk=%s: %s",
                request.user.pk, pk, exc,
            )
            return Response(
                {"error": "An unexpected error occurred."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        output = BankAccountOutputSerializer().to_representation(account)
        return Response(
            {"message": "Default bank account updated.", "data": output},
            status=status.HTTP_200_OK,
        )
