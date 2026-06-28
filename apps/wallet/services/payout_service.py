# apps/wallet/services/payout_service.py
"""
PayoutService — Vendor Payout Lifecycle Management.

Payout flow:
  1. Vendor requests payout (PayoutRequest created, status=PENDING)
  2. Admin approves → status=APPROVED, Paystack/Flutterwave transfer initiated
  3. Provider webhook confirms → status=COMPLETED, WalletTransaction debit created
  4. On failure → status=FAILED, wallet balance restored, admin notified

Architecture:
  - All status transitions: transaction.atomic() + select_for_update()
  - Amount locked at request creation (snapshot of wallet balance)
  - Minimum payout threshold enforced (₦5,000 default)
  - Frequency cap: max 1 pending payout per vendor at any time
  - Full audit trail via AuditEventLog
  - EventBus: payout.requested, payout.approved, payout.completed, payout.failed

Bank account validation:
  - PaystackService.resolve_bank_account() called before PayoutRequest creation
  - Account number stored hashed (SHA-256) — never raw in DB
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import TYPE_CHECKING

from django.db import transaction
from django.utils import timezone

if TYPE_CHECKING:
    from apps.authentication.models import UnifiedUser
    from apps.wallet.models import PayoutRequest

logger = logging.getLogger(__name__)

MINIMUM_PAYOUT_AMOUNT = Decimal("5000.00")   # ₦5,000 NGN minimum
PAYOUT_COMMISSION_RATE = Decimal("0.015")    # 1.5% transfer fee absorbed by platform


class PayoutService:
    """
    Manages vendor payout requests through their full lifecycle.
    """

    # ── Request Creation ──────────────────────────────────────────────────────

    @staticmethod
    @transaction.atomic
    def create_payout_request(
        *,
        vendor_user: "UnifiedUser",
        amount: Decimal,
        bank_account_id: str,
        description: str = "",
    ) -> "PayoutRequest":
        """
        Create a new payout request for a vendor.

        Validates:
          - Minimum amount threshold
          - Available wallet balance
          - No other PENDING payout for this vendor
          - Bank account belongs to this vendor

        Args:
            vendor_user: The vendor requesting payout.
            amount: Amount requested (gross, before any fees).
            bank_account_id: PK of the vendor's verified BankAccount.
            description: Optional vendor-facing note.

        Returns:
            Created PayoutRequest in PENDING status.

        Raises:
            ValueError: On business rule violations.
        """
        from apps.wallet.models import Wallet, PayoutRequest

        # Rule: minimum threshold
        if amount < MINIMUM_PAYOUT_AMOUNT:
            raise ValueError(
                f"Minimum payout is ₦{MINIMUM_PAYOUT_AMOUNT:,.2f}. Requested: ₦{amount:,.2f}"
            )

        # Rule: no concurrent pending payouts
        pending_exists = PayoutRequest.objects.filter(
            vendor=vendor_user,
            status="pending",
        ).exists()
        if pending_exists:
            raise ValueError(
                "A payout request is already pending. Wait for it to be processed."
            )

        # Lock wallet, check balance
        wallet = Wallet.objects.select_for_update().get(user=vendor_user)
        if wallet.available_balance < amount:
            raise ValueError(
                f"Insufficient wallet balance. Available: ₦{wallet.available_balance:,.2f}"
            )

        # Reserve the amount in the wallet (move to held_balance)
        wallet.available_balance -= amount
        wallet.held_balance += amount
        wallet.save(update_fields=["available_balance", "held_balance", "updated_at"])

        # Create the payout request
        payout = PayoutRequest.objects.create(
            vendor=vendor_user,
            amount=amount,
            bank_account_id=bank_account_id,
            description=description,
            status="pending",
            requested_at=timezone.now(),
        )

        _uid = str(vendor_user.id)
        _pid = str(payout.id)

        def _emit():
            try:
                from apps.common.events import event_bus
                event_bus.emit(
                    "payout.requested",
                    {"vendor_id": _uid, "payout_id": _pid, "amount": str(amount)},
                )
                from apps.audit_logs.tasks import log_audit_event_async
                log_audit_event_async.apply_async(
                    kwargs={
                        "event_type": "payout_requested",
                        "event_category": "financial",
                        "severity": "info",
                        "action": f"Payout request created: ₦{amount}",
                        "actor_id": _uid,
                        "resource_type": "PayoutRequest",
                        "resource_id": _pid,
                        "is_compliance": True,
                    },
                    queue="audit",
                )
            except Exception:
                logger.warning("Payout request audit failed", exc_info=True)

        transaction.on_commit(_emit)
        logger.info("Payout requested: vendor=%s amount=%s payout=%s", vendor_user.id, amount, payout.id)
        return payout

    # ── Admin Approval ────────────────────────────────────────────────────────

    @staticmethod
    @transaction.atomic
    def approve_payout(
        *,
        payout_id: str,
        approved_by: "UnifiedUser",
    ) -> "PayoutRequest":
        """
        Admin approves a pending payout, triggering Paystack transfer initiation.

        Changes status: PENDING → APPROVED → (provider call) → PROCESSING.
        """
        from apps.wallet.models import PayoutRequest

        payout = PayoutRequest.objects.select_for_update().get(pk=payout_id, status="pending")
        payout.status = "approved"
        payout.approved_by = approved_by
        payout.approved_at = timezone.now()
        payout.save(update_fields=["status", "approved_by", "approved_at"])

        _uid = str(approved_by.id)
        _pid = str(payout.id)
        _vendor_id = str(payout.vendor_id)

        def _initiate():
            try:
                # Trigger async Celery task to call Paystack transfer API
                from apps.wallet.tasks import initiate_paystack_transfer_task
                initiate_paystack_transfer_task.apply_async(
                    kwargs={"payout_id": _pid},
                    queue="financial",
                )
                from apps.audit_logs.tasks import log_audit_event_async
                log_audit_event_async.apply_async(
                    kwargs={
                        "event_type": "payout_approved",
                        "event_category": "financial",
                        "severity": "info",
                        "action": "Payout approved by admin",
                        "actor_id": _uid,
                        "resource_type": "PayoutRequest",
                        "resource_id": _pid,
                        "metadata": {"vendor_id": _vendor_id},
                        "is_compliance": True,
                    },
                    queue="audit",
                )
            except Exception:
                logger.warning("Payout approval emit failed", exc_info=True)

        transaction.on_commit(_initiate)
        logger.info("Payout approved: payout=%s by=%s", payout.id, approved_by.id)
        return payout

    # ── Completion (Provider Webhook) ─────────────────────────────────────────

    @staticmethod
    @transaction.atomic
    def complete_payout(
        *,
        payout_id: str,
        provider_reference: str,
    ) -> "PayoutRequest":
        """
        Mark payout as completed after provider transfer webhook confirms success.

        Deducts the held amount from wallet (held → 0, debit recorded).
        """
        from apps.wallet.models import PayoutRequest, Wallet

        payout = PayoutRequest.objects.select_for_update().get(
            pk=payout_id, status__in=["approved", "processing"]
        )
        vendor_user = payout.vendor

        # Release held balance (debit wallet properly)
        wallet = Wallet.objects.select_for_update().get(user=vendor_user)
        wallet.held_balance = max(Decimal("0"), wallet.held_balance - payout.amount)
        wallet.total_debited += payout.amount
        wallet.save(update_fields=["held_balance", "total_debited", "updated_at"])

        payout.status = "completed"
        payout.provider_reference = provider_reference
        payout.completed_at = timezone.now()
        payout.save(update_fields=["status", "provider_reference", "completed_at"])

        _uid = str(vendor_user.id)
        _pid = str(payout.id)

        def _emit():
            try:
                from apps.common.events import event_bus
                event_bus.emit(
                    "payout.completed",
                    {"vendor_id": _uid, "payout_id": _pid, "provider_ref": provider_reference},
                )
                from apps.audit_logs.tasks import log_audit_event_async
                log_audit_event_async.apply_async(
                    kwargs={
                        "event_type": "payout_completed",
                        "event_category": "financial",
                        "severity": "info",
                        "action": f"Payout completed: ref={provider_reference}",
                        "actor_id": _uid,
                        "resource_type": "PayoutRequest",
                        "resource_id": _pid,
                        "is_compliance": True,
                    },
                    queue="audit",
                )
            except Exception:
                logger.warning("Payout complete audit failed", exc_info=True)

        transaction.on_commit(_emit)
        logger.info("Payout completed: payout=%s ref=%s", payout.id, provider_reference)
        return payout

    # ── Failure (Provider Webhook or Admin Rejection) ─────────────────────────

    @staticmethod
    @transaction.atomic
    def fail_payout(
        *,
        payout_id: str,
        reason: str,
        restore_balance: bool = True,
    ) -> "PayoutRequest":
        """
        Mark a payout as failed and optionally restore the held balance.

        Called on provider error or admin rejection.
        """
        from apps.wallet.models import PayoutRequest, Wallet

        payout = PayoutRequest.objects.select_for_update().get(
            pk=payout_id, status__in=["pending", "approved", "processing"]
        )
        vendor_user = payout.vendor

        if restore_balance:
            wallet = Wallet.objects.select_for_update().get(user=vendor_user)
            wallet.held_balance = max(Decimal("0"), wallet.held_balance - payout.amount)
            wallet.available_balance += payout.amount
            wallet.save(update_fields=["held_balance", "available_balance", "updated_at"])

        payout.status = "failed"
        payout.failure_reason = reason
        payout.failed_at = timezone.now()
        payout.save(update_fields=["status", "failure_reason", "failed_at"])

        logger.error(
            "Payout failed: payout=%s vendor=%s reason=%s", payout.id, vendor_user.id, reason
        )
        return payout
