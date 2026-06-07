# apps/wallet/services/company_payout.py
"""
CompanyWithdrawalService — Fashionistar Company Commission Payout Engine.

This service handles the exclusive, high-security withdrawal of company
platform commissions from the Fashionistar Company Wallet to a designated
company bank account.

Security Architecture — "Double-Door" Lock:
    Door 1 — Identity Lock (Email Verification):
        The requesting user MUST be ``fashionistarclothings@outlook.com``.
        Any other email is rejected with a CRITICAL security log event.

    Door 2 — Domain Lock (Keyword Verification):
        The destination bank account name MUST contain the keyword
        ``"FASHIONISTAR"``. This prevents rogue admins from redirecting
        company commissions to personal accounts.

Financial Architecture:
    - ``select_for_update()`` locks the company wallet row before any balance
      mutation to prevent race conditions at 10k+ RPS.
    - ``transaction.on_commit()`` ensures the EventBus and audit logs are only
      notified for COMMITTED withdrawals — never on rolled-back transactions.
    - Immutable ledger entry created via ``TransactionLedgerService`` for
      PCI-DSS and CBN compliance.

Integration Guide::

    from apps.wallet.services.company_payout import CompanyWithdrawalService

    # Called from Ninja async endpoint (see wallet/apis/async_/mutation_views.py)
    result = CompanyWithdrawalService.request_company_payout(
        user=request.auth,          # Must be fashionistarclothings@outlook.com
        amount=Decimal("500000.00"),
        bank_code="044",
        account_number="0123456789",
        account_name="FASHIONISTAR CLOTHINGS LTD",
        request=request,
    )
    # result = {"transaction_id": "...", "reference": "...", "status": "..."}

Permissions:
    This service is also gated at the API layer by ``IsCompanyFinancialAdmin``
    (see ``apps/wallet/permissions.py``) as a belt-and-suspenders guard.

EventBus Events (emitted on transaction.on_commit):
    ``wallet.company_payout_requested`` — commission withdrawal initiated.
"""
from __future__ import annotations

import logging
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction as db_transaction
from django.utils import timezone

from apps.common.events import event_bus
from apps.wallet.models import Wallet
from apps.wallet.services.provisioning import COMPANY_EMAIL, WalletProvisioningService
from apps.wallet.services.verification import assert_company_payout_eligibility

logger = logging.getLogger(__name__)


class CompanyWithdrawalService:
    """High-security company commission withdrawal service.

    Only the primary company superuser (``fashionistarclothings@outlook.com``)
    can trigger a payout. The destination account name MUST contain the keyword
    ``"FASHIONISTAR"`` as a second-factor domain verification.
    """

    @staticmethod
    @db_transaction.atomic
    def request_company_payout(
        *,
        user,
        amount: Decimal,
        bank_code: str,
        account_number: str,
        account_name: str,
        idempotency_key: str = "",
        request=None,
    ) -> dict:
        """Withdraw company commission balance to the designated company bank account.

        Security Gates (in order):
            1. Double-Door verification (email + account name keyword).
            2. Idempotency check — prevents duplicate ledger rows.
            3. Company wallet SELECT FOR UPDATE lock.
            4. Available balance sufficiency check.
            5. Atomic balance debit + immutable ledger entry.

        Args:
            user: The authenticated ``UnifiedUser`` requesting the payout.
                  MUST be ``fashionistarclothings@outlook.com``.
            amount: Positive ``Decimal`` amount to withdraw.
            bank_code: Paystack/Flutterwave bank code (e.g. ``"044"``).
            account_number: Destination company bank account number.
            account_name: Destination account holder name. MUST contain
                          ``"FASHIONISTAR"`` (Door 2).
            idempotency_key: Optional UUID for duplicate-request protection.
            request: Optional HTTP request for IP/device metadata capture.

        Returns:
            dict: Keys ``transaction_id``, ``reference``, ``status``,
                ``amount``, ``available_balance``.

        Raises:
            ValueError: If either security door fails.
            ValidationError: If the wallet is inactive or balance is insufficient.
        """
        from apps.transactions.models import TransactionDirection, TransactionStatus, TransactionType
        from apps.transactions.services import TransactionLedgerService

        # ── Double-Door Security Verification ────────────────────────────────
        # Raises ValueError immediately if either door fails.
        # Logged at CRITICAL level inside assert_company_payout_eligibility.
        assert_company_payout_eligibility(
            user_email=user.email,
            account_name=account_name,
        )

        # ── Idempotency Check ─────────────────────────────────────────────────
        if idempotency_key:
            from apps.transactions.models import Transaction
            existing = Transaction.objects.filter(
                idempotency_key=idempotency_key,
                transaction_type=TransactionType.PAYOUT,
            ).first()
            if existing:
                logger.info(
                    "Idempotent company payout: returning existing txn=%s key=%s",
                    existing.pk, idempotency_key,
                )
                return {
                    "transaction_id": str(existing.pk),
                    "reference": existing.reference,
                    "status": existing.status,
                    "amount": str(existing.amount),
                    "available_balance": str(existing.from_balance_after or "0.00"),
                }

        # ── Lock the Company Wallet Row ───────────────────────────────────────
        # ensure_company_wallet() enforces the link to COMPANY_EMAIL singleton.
        company_wallet_provisioned = WalletProvisioningService.ensure_company_wallet()
        company_wallet: Wallet = Wallet.objects.select_for_update().get(
            pk=company_wallet_provisioned.pk
        )

        # ── Active Status Guard ───────────────────────────────────────────────
        from apps.wallet.models import WalletStatus
        if company_wallet.status != WalletStatus.ACTIVE:
            raise ValidationError(
                f"Company wallet is not active (status={company_wallet.status}). "
                "Contact technical support."
            )

        # ── Balance Sufficiency Check ─────────────────────────────────────────
        if company_wallet.available_balance < amount:
            raise ValidationError(
                f"Insufficient company commission balance. "
                f"Available: ₦{company_wallet.available_balance:,.2f}, "
                f"Requested: ₦{amount:,.2f}."
            )

        # ── Atomic Balance Debit ──────────────────────────────────────────────
        before_available = company_wallet.available_balance
        company_wallet.balance -= amount
        company_wallet.available_balance -= amount
        company_wallet.daily_spent += amount
        company_wallet.monthly_spent += amount
        company_wallet.last_transaction_at = timezone.now()
        company_wallet.save(
            update_fields=[
                "balance",
                "available_balance",
                "daily_spent",
                "monthly_spent",
                "last_transaction_at",
                "updated_at",
            ]
        )

        # ── Immutable Ledger Entry (PCI-DSS / CBN Compliance) ─────────────────
        ref = f"company-payout:{company_wallet.pk}:{timezone.now().timestamp()}"
        txn = TransactionLedgerService.create_entry(
            transaction_type=TransactionType.PAYOUT,
            status=TransactionStatus.PROCESSING,
            direction=TransactionDirection.OUTBOUND,
            amount=amount,
            net_amount=amount,
            from_user=user,
            from_wallet=company_wallet,
            reference=ref,
            idempotency_key=idempotency_key,
            description=(
                f"Company commission payout to {account_name} "
                f"({bank_code} •••• {account_number[-4:]})"
            ),
            from_balance_before=before_available,
            from_balance_after=company_wallet.available_balance,
            metadata={
                "bank_code": bank_code,
                "account_number_last4": account_number[-4:],
                "account_name": account_name,
                "payout_state": "pending_provider_execution",
                "security_verified": True,
                "email_door": COMPANY_EMAIL,
                "keyword_door": "FASHIONISTAR",
                # Telemetry: capture IP and device for audit trail
                "ip_address": (
                    request.META.get("REMOTE_ADDR", "") if request else ""
                ),
                "user_agent": (
                    request.META.get("HTTP_USER_AGENT", "") if request else ""
                ),
            },
            request=request,
        )

        # ── EventBus + Compliance Audit (on_commit) ───────────────────────────
        # These only fire if the DB transaction commits — never on rollback.
        _txn_id = str(txn.pk)
        _uid = str(user.pk)
        _wid = str(company_wallet.pk)
        _amt = str(amount)
        _ref = txn.reference

        def _on_company_payout_commit():
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
                    "wallet_audit.log_withdrawal_requested (company) failed silently",
                    exc_info=True,
                )
            event_bus.emit(
                "wallet.company_payout_requested",
                transaction_id=_txn_id,
                user_id=_uid,
                wallet_id=_wid,
                amount=_amt,
                reference=_ref,
                account_name=account_name,
                bank_code=bank_code,
            )
            logger.critical(
                "COMPANY PAYOUT INITIATED: user=%s amount=%s bank=%s ref=%s",
                user.email, amount, bank_code, _ref,
            )

        db_transaction.on_commit(_on_company_payout_commit)
        logger.info(
            "Company payout requested: user=%s amount=%s bank=%s txn=%s",
            user.email, amount, bank_code, txn.pk,
        )

        return {
            "transaction_id": str(txn.pk),
            "reference": txn.reference,
            "status": txn.status,
            "amount": str(amount),
            "available_balance": str(company_wallet.available_balance),
        }
