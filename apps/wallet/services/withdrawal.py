# apps/wallet/services/withdrawal.py
"""
WalletWithdrawalService — KYC-Gated Wallet-to-Bank Withdrawal Requests.

Architecture:
    This service creates a durable ledger row and moves funds from
    available_balance → pending_balance atomically.  Provider transfer
    execution and reconciliation can run later without losing the original
    authenticated request context.

Security Gates (applied in order):
    1. KYC Gate:        ``assert_kyc_approved(user)`` — identity must be verified.
    2. Min/Max Limits:  Configurable per GlobalPlatformSettings (₦100 – ₦5,000,000).
    3. Idempotency:     ``idempotency_key`` prevents duplicate withdrawal ledger rows.
    4. PIN Gate:        User's transaction PIN must pass bcrypt verification.
    5. Balance Guard:   ``available_balance >= amount`` enforced under row lock.

Integration Guide::

    from apps.wallet.services.withdrawal import WalletWithdrawalService

    result = WalletWithdrawalService.request_withdrawal(
        user=request.user,
        amount=Decimal("50000.00"),
        pin="1234",
        bank_code="044",
        account_number="0123456789",
        account_name="John Doe",
        idempotency_key=request.headers.get("Idempotency-Key", ""),
        request=request,
    )
    # result contains: transaction_id, reference, status,
    #                  amount, available_balance, pending_balance

EventBus Events (emitted on transaction.on_commit):
    ``wallet.withdrawal_requested`` — withdrawal created, pending provider.
"""
from __future__ import annotations

import logging
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction as db_transaction
from django.utils import timezone

from apps.common.events import event_bus
from apps.global_platform_settings.cache import get_platform_settings
from apps.wallet.models import WalletStatus
from apps.wallet.services.balance import WalletBalanceService
from apps.wallet.services.provisioning import WalletProvisioningService

logger = logging.getLogger(__name__)


class WalletWithdrawalService:
    """KYC-gated wallet-to-bank withdrawal request service.

    This service creates a durable ledger row and moves funds from available to
    pending balance. Provider transfer execution/reconciliation can safely run
    later without losing the original authenticated request context.

    Note:
        This service handles CLIENT and VENDOR withdrawals only.
        Company commission withdrawals are handled by ``CompanyWithdrawalService``.
    """

    @classmethod
    @db_transaction.atomic
    def request_withdrawal(
        cls,
        *,
        user,
        amount: Decimal,
        pin: str,
        bank_code: str,
        account_number: str,
        account_name: str,
        idempotency_key: str = "",
        request=None,
    ) -> dict:
        """Create a pending withdrawal after all security gates pass.

        Traversal (Wave-4 canonical):
            ``request.user.kyc_submission`` — gates the fund exit.
            ``request.user.financial_wallets`` — locks and updates the wallet.

        Args:
            user: A ``UnifiedUser`` instance (client or vendor).
            amount: Positive ``Decimal`` amount to withdraw.
            pin: The user's plaintext transaction PIN for authorisation.
            bank_code: Bank code (e.g. ``"044"`` for Access Bank).
            account_number: Destination bank account number.
            account_name: Destination bank account holder name.
            idempotency_key: Optional UUID string for duplicate-request protection.
            request: Optional HTTP request for audit metadata (IP, device).

        Returns:
            dict: Keys ``transaction_id``, ``reference``, ``status``,
                ``amount``, ``available_balance``, ``pending_balance``.

        Raises:
            ValidationError: If any security gate fails.
        """
        from apps.kyc.services import assert_kyc_approved
        from apps.transactions.models import TransactionDirection, TransactionStatus, TransactionType
        from apps.transactions.services import TransactionLedgerService

        # ── Gate 1: KYC — identity must be verified ───────────────────────────
        assert_kyc_approved(user)

        # ── Gate 2: Amount Limits (from GlobalPlatformSettings) ───────────────
        cfg = get_platform_settings()
        if amount < cfg.min_withdrawal_ngn:
            raise ValidationError(
                f"Minimum withdrawal is ₦{cfg.min_withdrawal_ngn:,.2f} NGN."
            )
        if amount > cfg.max_withdrawal_ngn:
            raise ValidationError(
                f"Maximum withdrawal is ₦{cfg.max_withdrawal_ngn:,.2f} NGN."
            )

        # ── Gate 3: Idempotency — prevent duplicate ledger rows ───────────────
        if idempotency_key:
            from apps.transactions.models import Transaction
            existing = Transaction.objects.filter(
                idempotency_key=idempotency_key,
                transaction_type=TransactionType.PAYOUT,
            ).first()
            if existing:
                logger.info(
                    "Idempotent withdrawal: returning existing txn=%s key=%s",
                    existing.pk, idempotency_key,
                )
                return {
                    "transaction_id": str(existing.pk),
                    "reference": existing.reference,
                    "status": existing.status,
                    "amount": str(existing.amount),
                    "available_balance": str(existing.from_balance_after or "0.00"),
                    "pending_balance": "0.00",
                }

        # ── Gate 4+5: Wallet lock → PIN verify → Balance check ───────────────
        provisioned = WalletProvisioningService.ensure_wallet(user, request=request)
        wallet = user.financial_wallets.select_for_update().get(pk=provisioned.pk)

        WalletBalanceService._assert_active(wallet)

        if not wallet.verify_pin(pin):
            raise ValidationError("Invalid transaction PIN.")

        if wallet.available_balance < amount:
            raise ValidationError(
                f"Insufficient available balance. "
                f"Available: ₦{wallet.available_balance:,.2f}, "
                f"Required: ₦{amount:,.2f}."
            )

        # ── Atomic balance mutation ───────────────────────────────────────────
        before_available = wallet.available_balance
        wallet.available_balance -= amount
        wallet.pending_balance += amount
        wallet.last_transaction_at = timezone.now()
        wallet.save(
            update_fields=[
                "available_balance",
                "pending_balance",
                "last_transaction_at",
                "updated_at",
            ]
        )

        # ── Immutable ledger entry (PCI-DSS / CBN compliance) ─────────────────
        ref = f"wallet-withdrawal:{wallet.pk}:{timezone.now().timestamp()}"
        txn = TransactionLedgerService.create_entry(
            transaction_type=TransactionType.PAYOUT,
            status=TransactionStatus.PROCESSING,
            direction=TransactionDirection.OUTBOUND,
            amount=amount,
            net_amount=amount,
            from_user=user,
            from_wallet=wallet,
            reference=ref,
            idempotency_key=idempotency_key,
            description="Wallet withdrawal request pending provider payout.",
            from_balance_before=before_available,
            from_balance_after=wallet.available_balance,
            metadata={
                "bank_code": bank_code,
                # Store last 4 digits only — never store full account number
                "account_number_last4": account_number[-4:],
                "account_name": account_name,
                "payout_state": "pending_provider_execution",
                "ip_address": getattr(getattr(request, "META", {}), "get", lambda k, d=None: d)(
                    "REMOTE_ADDR", ""
                ) if request else "",
            },
            request=request,
        )

        # ── EventBus + compliance audit (on_commit only — never on rollback) ──
        _txn_id = str(txn.pk)
        _uid = str(user.pk)
        _wid = str(wallet.pk)
        _amt = str(amount)
        _ref = txn.reference

        def _on_withdrawal_commit():
            try:
                from apps.audit_logs.services.wallet import wallet_audit
                wallet_audit.log_withdrawal_requested(
                    actor=user,
                    wallet_id=_wid,
                    transaction_id=_txn_id,
                    amount=_amt,
                    bank_code=bank_code,
                    account_number_last4=account_number[-4:],
                    request=request,
                )
            except Exception:
                logger.warning(
                    "wallet_audit.log_withdrawal_requested failed silently",
                    exc_info=True,
                )
            event_bus.emit(
                "wallet.withdrawal_requested",
                transaction_id=_txn_id,
                user_id=_uid,
                wallet_id=_wid,
                amount=_amt,
                reference=_ref,
            )

        db_transaction.on_commit(_on_withdrawal_commit)
        logger.info(
            "Withdrawal requested: user=%s amount=%s bank=%s txn=%s",
            user.pk, amount, bank_code, txn.pk,
        )

        return {
            "transaction_id": str(txn.pk),
            "reference": txn.reference,
            "status": txn.status,
            "amount": str(amount),
            "available_balance": str(wallet.available_balance),
            "pending_balance": str(wallet.pending_balance),
        }
