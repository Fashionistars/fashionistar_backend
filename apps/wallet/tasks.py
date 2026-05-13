# apps/wallet/tasks.py
"""
Celery tasks for the Wallet domain.

Tasks:
  process_payout_task — Poll a payment provider for a PROCESSING PAYOUT
                         transaction, then confirm or fail it, moving
                         pending_balance → 0 accordingly.

Architecture:
  - All DB mutations go through the existing WalletBalanceService helpers
    and write immutable TransactionLedger entries (CBN compliance).
  - Redis / provider outages surface as retryable task failures — the
    underlying ledger row keeps `status=PROCESSING` and will be retried
    automatically up to MAX_RETRIES times with exponential back-off.
  - All operations are fail-safe: a crashed worker leaves the wallet in a
    consistent PROCESSING state; a supervisor re-queue will pick it up.

CBN Compliance Note:
  Funds remain in pending_balance until this task confirms/fails the
  provider transfer.  The immutable PAYOUT ledger row created by
  WalletWithdrawalService.request_withdrawal() is updated in-place
  (status field only) — no rows are deleted.
"""
from __future__ import annotations

import logging
from decimal import Decimal

from celery import shared_task
from django.db import transaction as db_transaction
from django.utils import timezone

logger = logging.getLogger(__name__)

# Configurable retry policy
MAX_RETRIES = 5
RETRY_BACKOFF = 120  # seconds (doubles via Celery's max_retries countdown)


@shared_task(
    bind=True,
    max_retries=MAX_RETRIES,
    default_retry_delay=RETRY_BACKOFF,
    name="wallet.process_payout",
    acks_late=True,  # only ack after successful completion to prevent loss
)
def process_payout_task(self, transaction_id: str) -> dict:
    """
    Poll the payment provider for a PAYOUT transaction and finalize its state.

    Flow:
        1. Load the Transaction (must be PROCESSING + PAYOUT type).
        2. Call the provider SDK to query transfer status.
        3a. If provider confirms SUCCESS → mark COMPLETED, clear pending_balance.
        3b. If provider reports FAILURE  → mark FAILED, restore to available_balance.
        3c. If provider is still PENDING → retry with exponential back-off.
        4. Fire a compliance audit trail event (CBN/GDPR).
        5. Send a user notification (in-app + email) with the final status.

    Args:
        transaction_id: The UUID of the TransactionLedger row (PAYOUT, PROCESSING).

    Returns:
        dict: Final status info for logging/monitoring.
    """
    from apps.transactions.models import TransactionStatus, TransactionType

    logger.info("process_payout_task: starting txn=%s attempt=%s", transaction_id, self.request.retries)

    # ── 1. Load the ledger row ────────────────────────────────────────────────
    try:
        from apps.transactions.models import Transaction
        txn = Transaction.objects.select_related("from_wallet", "from_user").get(
            id=transaction_id,
            transaction_type=TransactionType.PAYOUT,
        )
    except Exception as exc:
        logger.error("process_payout_task: txn %s not found: %s", transaction_id, exc)
        return {"error": str(exc)}

    if txn.status not in {TransactionStatus.PROCESSING, "processing"}:
        logger.info(
            "process_payout_task: txn=%s already in status=%s — skipping",
            transaction_id,
            txn.status,
        )
        return {"status": txn.status, "skipped": True}

    # ── 2. Query the payment provider ─────────────────────────────────────────
    provider_status = _query_provider(txn)

    if provider_status == "pending":
        # Still processing on the provider side — schedule a retry
        logger.info("process_payout_task: txn=%s still pending, retrying", transaction_id)
        raise self.retry(countdown=RETRY_BACKOFF * (2 ** self.request.retries))

    # ── 3. Finalize the transaction ───────────────────────────────────────────
    if provider_status == "success":
        _confirm_payout(txn)
        _notify_user(txn, success=True)
        _audit_payout(txn, success=True)
        logger.info("process_payout_task: txn=%s CONFIRMED", transaction_id)
        return {"transaction_id": transaction_id, "final_status": "completed"}

    # provider_status == "failed"
    _fail_payout(txn)
    _notify_user(txn, success=False)
    _audit_payout(txn, success=False)
    logger.warning("process_payout_task: txn=%s FAILED", transaction_id)
    return {"transaction_id": transaction_id, "final_status": "failed"}


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

def _query_provider(txn) -> str:
    """
    Query the payment provider for the current transfer status.

    Returns one of: 'success', 'failed', 'pending'

    Stub implementation — replace with real Paystack/Flutterwave SDK call:

        import paystack
        resp = paystack.Transfer.verify(reference=txn.reference)
        if resp["data"]["status"] == "success":
            return "success"
        elif resp["data"]["status"] in {"failed", "reversed"}:
            return "failed"
        return "pending"
    """
    meta = txn.metadata or {}
    provider_ref = meta.get("provider_reference", "") or txn.reference

    logger.debug(
        "_query_provider: checking ref=%s txn=%s [STUB — returns pending]",
        provider_ref,
        txn.id,
    )
    # ── STUB: always return 'pending' until real SDK is wired ─────────────────
    # Change to real SDK call here. Return 'success' | 'failed' | 'pending'.
    return "pending"


@db_transaction.atomic
def _confirm_payout(txn) -> None:
    """Mark the PAYOUT ledger row COMPLETED and zero out pending_balance."""
    from apps.transactions.models import TransactionStatus

    wallet = txn.from_wallet
    if wallet is None:
        return

    locked_wallet = wallet.__class__.objects.select_for_update().get(pk=wallet.pk)
    amount = txn.amount or Decimal("0.00")

    # Move pending_balance → 0, total balance already debited at withdrawal time
    locked_wallet.pending_balance = max(
        locked_wallet.pending_balance - amount, Decimal("0.00")
    )
    locked_wallet.last_transaction_at = timezone.now()
    locked_wallet.save(update_fields=["pending_balance", "last_transaction_at", "updated_at"])

    txn.status = TransactionStatus.COMPLETED
    txn.completed_at = timezone.now()
    txn.metadata = {**(txn.metadata or {}), "payout_state": "provider_confirmed"}
    txn.save(update_fields=["status", "completed_at", "metadata"])


@db_transaction.atomic
def _fail_payout(txn) -> None:
    """Mark the PAYOUT ledger row FAILED and restore funds to available_balance."""
    from apps.transactions.models import TransactionStatus

    wallet = txn.from_wallet
    if wallet is None:
        return

    locked_wallet = wallet.__class__.objects.select_for_update().get(pk=wallet.pk)
    amount = txn.amount or Decimal("0.00")

    # Reverse: pending_balance → 0, restore to available_balance
    locked_wallet.pending_balance = max(
        locked_wallet.pending_balance - amount, Decimal("0.00")
    )
    locked_wallet.available_balance += amount
    locked_wallet.last_transaction_at = timezone.now()
    locked_wallet.save(
        update_fields=[
            "pending_balance",
            "available_balance",
            "last_transaction_at",
            "updated_at",
        ]
    )

    txn.status = TransactionStatus.FAILED
    txn.metadata = {**(txn.metadata or {}), "payout_state": "provider_failed"}
    txn.save(update_fields=["status", "metadata"])


def _notify_user(txn, *, success: bool) -> None:
    """Fire an in-app notification for the payout result (fail-safe)."""
    try:
        from apps.notification.models import NotificationType
        from apps.notification.services import create_notification
        from apps.notification.models import NotificationChannel

        if txn.from_user is None:
            return

        amount_str = f"₦{txn.amount:,.2f}" if txn.amount else "Your funds"

        if success:
            create_notification(
                recipient=txn.from_user,
                notification_type=NotificationType.PAYOUT_COMPLETED,
                title="Withdrawal Successful 🎉",
                body=(
                    f"{amount_str} has been sent to your bank account. "
                    "It may take 1–3 business days to reflect."
                ),
                channel=NotificationChannel.IN_APP,
                metadata={"transaction_id": str(txn.pk), "amount": str(txn.amount)},
            )
        else:
            create_notification(
                recipient=txn.from_user,
                notification_type=NotificationType.PAYOUT_COMPLETED,
                title="Withdrawal Failed",
                body=(
                    f"Your withdrawal of {amount_str} could not be processed. "
                    "The funds have been returned to your wallet."
                ),
                channel=NotificationChannel.IN_APP,
                metadata={"transaction_id": str(txn.pk), "amount": str(txn.amount)},
            )
    except Exception as exc:
        logger.warning("process_payout_task: _notify_user failed: %s", exc)


def _audit_payout(txn, *, success: bool) -> None:
    """Write a compliance audit trail for the payout finalization (fail-safe)."""
    try:
        from apps.audit_logs.services.wallet import wallet_audit
        if success:
            wallet_audit.log_payout_confirmed(
                actor=txn.from_user,
                wallet_id=str(getattr(txn.from_wallet, "pk", "")),
                transaction_id=str(txn.pk),
                amount=str(txn.amount),
            )
        else:
            wallet_audit.log_payout_failed(
                actor=txn.from_user,
                wallet_id=str(getattr(txn.from_wallet, "pk", "")),
                transaction_id=str(txn.pk),
                amount=str(txn.amount),
            )
    except Exception as exc:
        logger.warning("process_payout_task: _audit_payout failed: %s", exc)
