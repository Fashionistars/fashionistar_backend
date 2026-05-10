# apps/payment/cash_service.py
"""
Cash / COD / In-store Payment Service
=======================================

Handles cash orders so commission compliance is enforced even when clients
pay outside the digital payment gateway.

───────────────────────────────────────────────────────────────────────
PROBLEM:
  Vendors could previously agree with clients to pay cash and skip the
  platform entirely — Fashionistar would never see the transaction and
  could not collect its commission.

SOLUTION — Three-step commission-safe cash flow:
  1. CLIENT creates a cash order → platform creates an escrow-hold marker
     with ``requires_cash_confirmation=True``.
  2. VENDOR delivers goods/service → must call ConfirmCashDeliveryView API
     with the client's one-time QR token.  The platform cannot be bypassed
     because the order remains in "awaiting_cash_confirmation" status until
     this step completes — the vendor's KYC / payouts remain blocked.
  3. PLATFORM auto-deducts commission from vendor wallet on confirmation.
     If the vendor's wallet balance is insufficient, a debt ledger entry is
     created and future payouts are blocked until cleared.

COD SECURITY MEASURES:
  • Client receives a one-time 6-digit confirmation code (or QR token) in
    the Fashionistar app after placing the order.  They show this to the
    vendor at delivery.
  • Vendor submits the code to the API.  The platform verifies it, records
    the delivery, and executes the commission deduction atomically.
  • If the vendor fails to confirm within ``cod_confirmation_window_hours``
    (configurable in PlatformSettings), the order is auto-flagged for
    support review and the vendor's payout dashboard shows a warning.
  • Clients can dispute — raising a full dispute case if vendor claimed
    delivery but client denies receiving goods.
"""
from __future__ import annotations

import logging
import secrets
from decimal import Decimal

from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import transaction as db_transaction
from django.utils import timezone

from apps.global_platform_settings.cache import get_platform_settings
from apps.payment.models import PaymentIntent, PaymentIntentStatus, PaymentProviderCode, PaymentPurpose
from apps.transactions.models import (
    CompanyRevenueEntry,
    RevenueCategory,
    Transaction,
    TransactionDirection,
    TransactionStatus,
    TransactionType,
)
from apps.transactions.services import TransactionLedgerService
from apps.wallet.services import WalletProvisioningService

logger = logging.getLogger("application")

_COD_TOKEN_PREFIX = "fashionistar:cod_token"
_COD_TOKEN_TTL_SECONDS = 60 * 60 * 24 * 3  # 72 hours default (overridden by PlatformSettings)


def _cod_token_key(order_id: str) -> str:
    return f"{_COD_TOKEN_PREFIX}:{order_id}"


class CashOrderService:
    """
    Orchestrates cash / COD / in-store payment lifecycle.
    All mutation methods are ``@db_transaction.atomic``.
    """

    # ── Step 1: Client creates a cash/COD order ───────────────────────────────

    @classmethod
    @db_transaction.atomic
    def create_cod_order(
        cls,
        *,
        user,
        amount: Decimal,
        order_id: str,
        currency: str = "NGN",
        is_in_store: bool = False,
        idempotency_key: str = "",
    ) -> dict:
        """
        Register a COD or in-store payment order.

        Returns:
            {
                "intent_id": str,
                "reference": str,
                "confirmation_token": str,   ← Client shows this to vendor
                "confirmation_expires_at": ISO datetime string,
                "provider": "cod" | "cash",
            }

        Raises:
            ValidationError: if COD/in-store is disabled in PlatformSettings.
        """
        cfg = get_platform_settings()
        if is_in_store and not cfg.in_store_payment_enabled:
            raise ValidationError("In-store payments are currently disabled on this platform.")
        if not is_in_store and not cfg.cod_enabled:
            raise ValidationError("Cash-on-delivery is currently disabled on this platform.")

        # Idempotency: if intent already exists for this order return early
        existing = PaymentIntent.objects.filter(order_id=order_id, provider__in=[PaymentProviderCode.COD, PaymentProviderCode.CASH]).first()
        if existing:
            token = cache.get(_cod_token_key(order_id)) or cls._issue_token(order_id, cfg)
            return cls._format_response(existing, token, cfg)

        reference = f"FSCOD_{secrets.token_urlsafe(20)}"
        provider = PaymentProviderCode.CASH if is_in_store else PaymentProviderCode.COD

        intent = PaymentIntent.objects.create(
            user=user,
            provider=provider,
            purpose=PaymentPurpose.ORDER_PAYMENT,
            amount=amount,
            currency=currency,
            status=PaymentIntentStatus.PENDING,
            reference=reference,
            order_id=order_id,
            idempotency_key=idempotency_key,
            metadata={
                "is_cod": not is_in_store,
                "is_in_store": is_in_store,
                "requires_cash_confirmation": True,
            },
        )

        token = cls._issue_token(order_id, cfg)
        logger.info("CashOrderService: Created %s intent ref=%s order=%s", provider, reference, order_id)
        return cls._format_response(intent, token, cfg)

    @staticmethod
    def _issue_token(order_id: str, cfg) -> str:
        """Generate and cache a 6-digit confirmation token for this order."""
        token = f"{secrets.randbelow(900000) + 100000:06d}"  # 100000-999999
        ttl = cfg.cod_confirmation_window_hours * 3600
        cache.set(_cod_token_key(order_id), token, ttl)
        return token

    @staticmethod
    def _format_response(intent: PaymentIntent, token: str, cfg) -> dict:
        from django.utils import timezone as tz
        import datetime
        expires_at = tz.now() + datetime.timedelta(hours=cfg.cod_confirmation_window_hours)
        return {
            "intent_id": str(intent.pk),
            "reference": intent.reference,
            "confirmation_token": token,
            "confirmation_expires_at": expires_at.isoformat(),
            "provider": intent.provider,
        }

    # ── Step 2: Vendor confirms delivery ──────────────────────────────────────

    @classmethod
    @db_transaction.atomic
    def confirm_cod_delivery(
        cls,
        *,
        order_id: str,
        vendor_user,
        client_token: str,
    ) -> dict:
        """
        Vendor submits client confirmation token to prove delivery.

        On success:
          1. PaymentIntent status → SUCCEEDED.
          2. Commission deducted from vendor wallet atomically.
          3. If vendor wallet insufficient → debt ledger entry created.
          4. COD token invalidated in Redis.

        Returns:
            {"success": True, "commission_deducted": "₦NNN.NN", "reference": str}

        Raises:
            ValidationError: invalid/expired token, intent not found, already confirmed.
        """
        cached_token = cache.get(_cod_token_key(order_id))
        if not cached_token:
            raise ValidationError("Confirmation token has expired. Request a new one from the client.")
        if cached_token != str(client_token).strip():
            raise ValidationError("Invalid confirmation token.")

        intent = PaymentIntent.objects.select_for_update().filter(
            order_id=order_id,
            provider__in=[PaymentProviderCode.COD, PaymentProviderCode.CASH],
        ).first()

        if not intent:
            raise ValidationError("No pending COD/cash payment found for this order.")
        if intent.status == PaymentIntentStatus.SUCCEEDED:
            raise ValidationError("This COD order has already been confirmed.")

        cfg = get_platform_settings()
        commission_rate = cfg.cod_platform_commission_rate
        commission_amount = (intent.amount * commission_rate).quantize(Decimal("0.01"))

        # Mark intent succeeded
        intent.status = PaymentIntentStatus.SUCCEEDED
        intent.metadata["confirmed_by_vendor"] = str(vendor_user.pk)
        intent.metadata["confirmed_at"] = timezone.now().isoformat()
        intent.metadata["commission_rate"] = str(commission_rate)
        intent.metadata["commission_amount"] = str(commission_amount)
        intent.save(update_fields=["status", "metadata", "updated_at"])

        # Deduct commission from vendor wallet
        company_wallet = WalletProvisioningService.ensure_company_wallet(intent.currency)
        vendor_wallet = WalletProvisioningService.ensure_wallet(vendor_user, intent.currency)

        if vendor_wallet.available_balance >= commission_amount:
            vendor_wallet.available_balance -= commission_amount
            vendor_wallet.balance -= commission_amount
            vendor_wallet.save(update_fields=["available_balance", "balance", "updated_at"])
            company_wallet.available_balance += commission_amount
            company_wallet.balance += commission_amount
            company_wallet.save(update_fields=["available_balance", "balance", "updated_at"])
            payment_status = "deducted"
        else:
            # Insufficient balance — create debt ledger entry
            logger.warning(
                "CashOrderService: Vendor %s wallet insufficient for COD commission ₦%s. Creating debt entry.",
                vendor_user.pk, commission_amount,
            )
            # Record a pending commission debt (negative vendor entry)
            payment_status = "debt_recorded"

        # Record commission ledger entry
        commission_txn = TransactionLedgerService.create_entry(
            transaction_type=TransactionType.COMMISSION,
            status=TransactionStatus.COMPLETED if payment_status == "deducted" else TransactionStatus.PENDING,
            direction=TransactionDirection.INBOUND,
            amount=commission_amount,
            net_amount=commission_amount,
            to_wallet=company_wallet,
            from_wallet=vendor_wallet,
            reference=f"{intent.reference}:cod-commission",
            order_id=order_id,
            description=f"Fashionistar COD commission ({commission_rate:.0%}) collected at delivery.",
            completed_at=timezone.now() if payment_status == "deducted" else None,
            metadata={
                "gross_amount": str(intent.amount),
                "commission_rate": str(commission_rate),
                "payment_status": payment_status,
            },
        )
        CompanyRevenueEntry.objects.create(
            transaction=commission_txn,
            category=RevenueCategory.ORDER_COMMISSION,
            amount=commission_amount,
            currency=company_wallet.currency,
            source_reference=intent.reference,
            metadata={"order_id": order_id, "type": "cod"},
        )

        # Invalidate the confirmation token
        cache.delete(_cod_token_key(order_id))

        logger.info(
            "CashOrderService: COD confirmed order=%s vendor=%s commission=₦%s status=%s",
            order_id, vendor_user.pk, commission_amount, payment_status,
        )

        return {
            "success": True,
            "reference": intent.reference,
            "commission_deducted": str(commission_amount),
            "payment_status": payment_status,
        }

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def resend_token(order_id: str) -> str:
        """
        Issue a fresh confirmation token for an existing COD order.
        Call this when client says they did not receive or lost their token.
        """
        cfg = get_platform_settings()
        intent = PaymentIntent.objects.filter(
            order_id=order_id,
            provider__in=[PaymentProviderCode.COD, PaymentProviderCode.CASH],
            status=PaymentIntentStatus.PENDING,
        ).first()
        if not intent:
            raise ValidationError("No pending COD order found for this order ID.")
        return CashOrderService._issue_token(order_id, cfg)
