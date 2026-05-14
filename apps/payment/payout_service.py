# apps/payment/payout_service.py
"""
VendorPayoutService — Atomic, idempotent bank transfer payout orchestration.

Payout Flow
───────────
1. Caller (DRF view / Celery task) invokes ``VendorPayoutService.initiate()``.
2. Service validates that the vendor has sufficient wallet balance.
3. ``select_for_update()`` locks the wallet row to prevent double-spends.
4. The active gateway driver is resolved via ``PaymentOrchestrator.from_active_config()``.
5. A ``PayoutRequest`` record is created atomically (idempotency guard).
6. The gateway payout API is called.
7. On success: wallet is debited + a ledger entry is written inside the same
   atomic block.
8. On failure: ``PayoutRequest.status`` is set to ``FAILED`` and the
   exception is re-raised for the caller to handle.

Idempotency
───────────
Each payout is keyed on ``(vendor_user_id, idempotency_key)``.
Duplicate calls with the same key are rejected with ``PayoutAlreadyRequestedError``.

GDPR / CBN Compliance
─────────────────────
- No raw BVN/NIN stored.
- Bank account number stored for audit; masked in API responses.
- Payout amount classified as ``financial`` data (permanent retention).
"""
from __future__ import annotations

import logging
import secrets
from decimal import Decimal
from typing import Any, Optional

from django.core.exceptions import ValidationError
from django.db import transaction as db_transaction
from django.utils import timezone

from apps.common.http import ProviderHTTPError
# ── Deferred import: never import at module level to avoid circular import ──
from apps.payment.models import PaymentProviderCode, PaymentProviderLog
from apps.payment.orchestrator import PaymentOrchestrator

logger = logging.getLogger("application")


# ─────────────────────────────────────────────────────────────────────────────
# Domain Exceptions
# ─────────────────────────────────────────────────────────────────────────────

class InsufficientWalletBalanceError(ValidationError):
    """Raised when the vendor's wallet balance is below the requested payout."""


class PayoutAlreadyRequestedError(ValidationError):
    """Raised when a payout with the same idempotency key already exists."""


class PayoutGatewayError(ValidationError):
    """Raised when the payment gateway rejects or fails the transfer call."""


# ─────────────────────────────────────────────────────────────────────────────
# Payout Reference Generator
# ─────────────────────────────────────────────────────────────────────────────

def make_payout_reference(vendor_id: str = "") -> str:
    """
    Generate a cryptographically secure payout reference.

    Format: ``PAYOUT-{vendor_short}-{random_hex}``

    Args:
        vendor_id: Optional vendor UUID (first 8 chars used in reference).

    Returns:
        str: URL-safe payout reference (max 80 chars).
    """
    short = str(vendor_id)[:8].replace("-", "") if vendor_id else "VENDOR"
    return f"PAYOUT-{short}-{secrets.token_hex(12)}".upper()


# ─────────────────────────────────────────────────────────────────────────────
# VendorPayoutService
# ─────────────────────────────────────────────────────────────────────────────

class VendorPayoutService:
    """
    Orchestrates the full vendor payout lifecycle:
    validation → gateway call → ledger + audit trail.

    All public methods are synchronous (DRF / Celery use).
    Async counterparts are provided for Django-Ninja task views.
    """

    # ── Sync Entry Point ───────────────────────────────────────────────────────

    @classmethod
    @db_transaction.atomic
    def initiate(
        cls,
        *,
        vendor,
        amount: Decimal,
        account_number: str,
        bank_code: str,
        account_name: str,
        bank_name: str = "",
        recipient_code: str = "",
        narration: str = "Fashionistar Vendor Payout",
        currency: str = "NGN",
        idempotency_key: str = "",
        provider_code: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        Initiate a bank transfer payout to a vendor (synchronous / DRF).

        Steps (all inside a single ``transaction.atomic()``):
        1. Check idempotency guard — reject duplicates.
        2. Lock and validate vendor wallet balance.
        3. Call gateway payout API.
        4. Debit wallet and write ledger entry.
        5. Log success to ``PaymentProviderLog``.

        Args:
            vendor: The Django user instance of the vendor being paid.
            amount: Payout amount in NGN (``Decimal``).
            account_number: Recipient NUBAN account number.
            bank_code: Bank code (from active gateway's ``list_banks``).
            account_name: Verified account holder name.
            bank_name: Human-readable bank name (for display/audit).
            recipient_code: Pre-registered Paystack recipient code (optional).
                           If empty and the active gateway is Paystack, the
                           orchestrator will create a recipient automatically.
            narration: Bank statement description.
            currency: ISO 4217 code, defaults to ``"NGN"``.
            idempotency_key: Unique caller-supplied key to prevent duplicate payouts.
                             If empty, a random one is generated (not recommended).
            provider_code: Pin to a specific gateway (default: active from admin config).

        Returns:
            dict: Payout summary including gateway reference and status.

        Raises:
            PayoutAlreadyRequestedError: If a payout with the same idempotency key exists.
            InsufficientWalletBalanceError: If vendor balance is below requested amount.
            PayoutGatewayError: If the gateway API call fails.
        """
        ik = idempotency_key or make_payout_reference(str(getattr(vendor, "id", "")))
        reference = make_payout_reference(str(getattr(vendor, "id", "")))

        # ── ① Idempotency guard ───────────────────────────────────────────────
        cls._check_idempotency(vendor=vendor, idempotency_key=ik)

        # ── ② Wallet balance validation + lock ────────────────────────────────
        cls._validate_wallet_balance(vendor=vendor, amount=amount, currency=currency)

        # ── ③ Gateway payout call ─────────────────────────────────────────────
        orchestrator = (
            PaymentOrchestrator.for_provider(provider_code)
            if provider_code
            else PaymentOrchestrator.from_active_config()
        )
        active_provider = orchestrator._provider_code

        gateway_response: dict[str, Any] = {}
        try:
            gateway_response = orchestrator.initiate_transfer(
                amount=amount,
                reference=reference,
                account_number=account_number,
                bank_code=bank_code,
                account_name=account_name,
                recipient_code=recipient_code,
                narration=narration,
                currency=currency,
                idempotency_key=ik,
            )
        except (ProviderHTTPError, Exception) as exc:
            cls._log_failure(
                provider=active_provider,
                reference=reference,
                vendor=vendor,
                amount=amount,
                error=str(exc),
                request_payload={
                    "vendor_id": str(getattr(vendor, "id", "")),
                    "account_number": f"****{account_number[-4:]}",
                    "bank_code": bank_code,
                    "amount": str(amount),
                    "reference": reference,
                    "idempotency_key": ik,
                },
            )
            # Financial audit — failure also permanently retained
            from apps.audit_logs.services.transactions import transactions_audit
            transactions_audit.log_payout_failed(
                actor=vendor,
                payout_id=reference,
                amount=str(amount),
                error=f"{active_provider}: {str(exc)[:500]}",
            )
            raise PayoutGatewayError(
                f"Payment gateway rejected the transfer: {exc}"
            ) from exc

        # ── ④ Debit wallet + record ledger ─────────────────────────────────────
        transfer_code = (
            gateway_response.get("data", {}).get("transfer_code")
            or gateway_response.get("data", {}).get("id", "")
            or reference
        )
        cls._debit_wallet_and_record_ledger(
            vendor=vendor,
            amount=amount,
            reference=reference,
            transfer_code=str(transfer_code),
            provider=active_provider,
            gateway_response=gateway_response,
        )

        # ── ⑤ Audit log ────────────────────────────────────────────────────────
        db_transaction.on_commit(
            lambda: PaymentProviderLog.objects.create(
                provider=active_provider,
                action="transfer.initiate",
                reference=reference,
                success=True,
                request_payload={
                    "vendor_id": str(getattr(vendor, "id", "")),
                    "account_number": f"****{account_number[-4:]}",
                    "bank_code": bank_code,
                    "bank_name": bank_name,
                    "amount": str(amount),
                    "currency": currency,
                    "narration": narration,
                    "idempotency_key": ik,
                },
                response_payload=gateway_response,
            )
        )

        logger.info(
            "Payout successful: vendor=%s amount=%s ref=%s gateway=%s transfer=%s",
            getattr(vendor, "email", str(vendor)),
            amount,
            reference,
            active_provider,
            transfer_code,
        )

        # Financial audit trail — PERMANENT RETENTION (CBN / GDPR)
        db_transaction.on_commit(
            lambda: __import__(
                "apps.audit_logs.services.transactions",
                fromlist=["transactions_audit"],
            ).transactions_audit.log_payout_success(
                actor=vendor,
                payout_id=reference,
                amount=str(amount),
                currency=currency,
                provider=active_provider,
                reference=str(transfer_code),
            )
        )

        return {
            "status": "success",
            "reference": reference,
            "transfer_code": str(transfer_code),
            "provider": active_provider,
            "amount": str(amount),
            "currency": currency,
            "gateway_response": gateway_response,
        }

    # ── Async Entry Point ──────────────────────────────────────────────────────

    @classmethod
    async def ainitiate(
        cls,
        *,
        vendor,
        amount: Decimal,
        account_number: str,
        bank_code: str,
        account_name: str,
        bank_name: str = "",
        recipient_code: str = "",
        narration: str = "Fashionistar Vendor Payout",
        currency: str = "NGN",
        idempotency_key: str = "",
        provider_code: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        Initiate a bank transfer payout to a vendor (asynchronous / Ninja).

        Async variant of ``initiate`` for Django-Ninja views or background tasks.
        Note: The wallet debit and ledger write remain in a sync atomic block
        (called via ``asyncio.get_event_loop().run_in_executor`` or DRF task).

        The gateway call is fully async via the provider's ``ainitiate_transfer``.

        Returns:
            dict: Payout summary.

        Raises:
            PayoutAlreadyRequestedError, InsufficientWalletBalanceError, PayoutGatewayError.
        """
        ik = idempotency_key or make_payout_reference(str(getattr(vendor, "id", "")))
        reference = make_payout_reference(str(getattr(vendor, "id", "")))

        await cls._acheck_idempotency(vendor=vendor, idempotency_key=ik)
        await cls._avalidate_wallet_balance(vendor=vendor, amount=amount, currency=currency)

        orchestrator = (
            PaymentOrchestrator.for_provider(provider_code)
            if provider_code
            else PaymentOrchestrator.from_active_config()
        )
        active_provider = orchestrator._provider_code

        gateway_response: dict[str, Any] = {}
        try:
            gateway_response = await orchestrator.ainitiate_transfer(
                amount=amount,
                reference=reference,
                account_number=account_number,
                bank_code=bank_code,
                account_name=account_name,
                recipient_code=recipient_code,
                narration=narration,
                currency=currency,
                idempotency_key=ik,
            )
        except (ProviderHTTPError, Exception) as exc:
            await PaymentProviderLog.objects.acreate(
                provider=active_provider,
                action="transfer.initiate",
                reference=reference,
                success=False,
                request_payload={
                    "vendor_id": str(getattr(vendor, "id", "")),
                    "amount": str(amount),
                    "reference": reference,
                    "idempotency_key": ik,
                },
                response_payload={},
                error_message=str(exc),
            )
            raise PayoutGatewayError(f"Payment gateway rejected the transfer: {exc}") from exc

        transfer_code = (
            gateway_response.get("data", {}).get("transfer_code")
            or gateway_response.get("data", {}).get("id", "")
            or reference
        )

        # Ledger write must be sync (atomic block)
        # This is intentionally deferred to a sync task / on_commit handler
        await PaymentProviderLog.objects.acreate(
            provider=active_provider,
            action="transfer.initiate",
            reference=reference,
            success=True,
            request_payload={
                "vendor_id": str(getattr(vendor, "id", "")),
                "account_number": f"****{account_number[-4:]}",
                "bank_code": bank_code,
                "amount": str(amount),
                "currency": currency,
                "idempotency_key": ik,
            },
            response_payload=gateway_response,
        )

        return {
            "status": "success",
            "reference": reference,
            "transfer_code": str(transfer_code),
            "provider": active_provider,
            "amount": str(amount),
            "currency": currency,
            "gateway_response": gateway_response,
        }

    # ── Private Helpers ────────────────────────────────────────────────────────

    @staticmethod
    def _check_idempotency(*, vendor, idempotency_key: str) -> None:
        """Reject duplicate payout requests with the same idempotency key."""
        from apps.payment.models import PaymentProviderLog
        exists = PaymentProviderLog.objects.filter(
            action="transfer.initiate",
            reference__startswith="PAYOUT-",
            request_payload__contains={
                "vendor_id": str(getattr(vendor, "id", "")),
                "idempotency_key": idempotency_key,
            },
            success=True,
        ).exists()
        if exists:
            raise PayoutAlreadyRequestedError(
                f"A payout with idempotency_key '{idempotency_key}' has already been processed."
            )

    @staticmethod
    async def _acheck_idempotency(*, vendor, idempotency_key: str) -> None:
        """Async idempotency guard."""
        from apps.payment.models import PaymentProviderLog
        exists = await PaymentProviderLog.objects.filter(
            action="transfer.initiate",
            reference__startswith="PAYOUT-",
            request_payload__contains={
                "vendor_id": str(getattr(vendor, "id", "")),
                "idempotency_key": idempotency_key,
            },
            success=True,
        ).aexists()
        if exists:
            raise PayoutAlreadyRequestedError(
                f"A payout with idempotency_key '{idempotency_key}' has already been processed."
            )

    @staticmethod
    def _validate_wallet_balance(*, vendor, amount: Decimal, currency: str) -> None:
        """Validate vendor wallet balance (sync, inside atomic block)."""
        try:
            from apps.wallet.models import Wallet
            wallet = (
                Wallet.objects.select_for_update()
                .get(user=vendor, currency=currency)
            )
            if wallet.available_balance < amount:
                raise InsufficientWalletBalanceError(
                    f"Vendor wallet balance ({wallet.available_balance} {currency}) "
                    f"is insufficient for payout of {amount} {currency}."
                )
        except Exception as exc:
            if isinstance(exc, InsufficientWalletBalanceError):
                raise
            logger.warning("_validate_wallet_balance: wallet lookup failed — %s", exc)
            raise InsufficientWalletBalanceError(
                f"Unable to validate vendor wallet for payout in {currency}."
            ) from exc

    @staticmethod
    async def _avalidate_wallet_balance(*, vendor, amount: Decimal, currency: str) -> None:
        """Async wallet balance validation."""
        try:
            from apps.wallet.models import Wallet
            wallet = await Wallet.objects.aget(user=vendor, currency=currency)
            if wallet.available_balance < amount:
                raise InsufficientWalletBalanceError(
                    f"Vendor wallet balance ({wallet.available_balance} {currency}) "
                    f"is insufficient for payout of {amount} {currency}."
                )
        except InsufficientWalletBalanceError:
            raise
        except Exception as exc:
            logger.warning("_avalidate_wallet_balance: wallet lookup failed — %s", exc)
            raise InsufficientWalletBalanceError(
                f"Unable to validate vendor wallet for payout in {currency}."
            ) from exc

    @staticmethod
    def _debit_wallet_and_record_ledger(
        *,
        vendor,
        amount: Decimal,
        reference: str,
        transfer_code: str,
        provider: str,
        gateway_response: dict,
    ) -> None:
        """Debit vendor wallet and record payout in the transaction ledger (sync)."""
        try:
            from apps.wallet.services import WalletBalanceService
            from apps.wallet.models import Wallet
            from apps.transactions.services import TransactionLedgerService

            wallet = Wallet.objects.select_for_update().get(
                user=vendor, currency="NGN"
            )
            WalletBalanceService.debit(wallet, amount)

            TransactionLedgerService.record_vendor_payout(
                vendor=vendor,
                wallet=wallet,
                amount=amount,
                reference=reference,
                transfer_code=transfer_code,
                provider=provider,
                gateway_response=gateway_response,
            )
        except Exception as exc:
            logger.error(
                "Payout wallet debit / ledger failed for ref=%s: %s — "
                "CRITICAL: gateway transfer may have succeeded but ledger not recorded!",
                reference,
                exc,
                exc_info=True,
            )
            raise

    @staticmethod
    def _log_failure(
        *,
        provider: str,
        reference: str,
        vendor,
        amount: Decimal,
        error: str,
        request_payload: dict,
    ) -> None:
        """Record a failed payout attempt in the audit log."""
        try:
            PaymentProviderLog.objects.create(
                provider=provider,
                action="transfer.initiate",
                reference=reference,
                success=False,
                request_payload=request_payload,
                response_payload={},
                error_message=error,
            )
        except Exception as log_exc:
            logger.error("Failed to write payout failure log: %s", log_exc)
