"""Transactions & Ledger domain audit helper — Wave B14."""
from __future__ import annotations


def log_transaction_created(
    *, actor, transaction_id: str, amount: str, currency: str = "NGN",
    tx_type: str = "", request=None
) -> None:
    """Record a ledger transaction creation.

    Args:
        actor: The user or system initiating the transaction.
        transaction_id: PaymentTransaction or TransactionLedgerEntry PK.
        amount: Amount as string.
        currency: ISO 4217 code.
        tx_type: Transaction type (credit, debit, escrow, refund).
        request: Django HttpRequest.
    """
    from apps.audit_logs.services.audit import AuditService
    from apps.audit_logs.models import EventType, EventCategory

    AuditService.log(
        event_type=EventType.TRANSACTION_CREATED,
        event_category=EventCategory.TRANSACTIONS,
        action=f"Transaction created: id={transaction_id} type={tx_type} amount={amount} {currency}",
        actor=actor,
        actor_role=getattr(actor, "user_type", None),
        resource_type="PaymentTransaction",
        resource_id=transaction_id,
        request=request,
        new_values={"amount": amount, "currency": currency, "type": tx_type},
        is_compliance=True,
        retention_days=-1,
    )


def log_ledger_entry_posted(
    *, actor=None, entry_id: str, wallet_id: str, amount: str,
    entry_type: str = "", currency: str = "NGN", request=None
) -> None:
    """Record a wallet ledger entry being posted.

    Args:
        actor: The user or system posting the entry.
        entry_id: WalletLedgerEntry PK.
        wallet_id: Parent Wallet PK.
        amount: Amount as string.
        entry_type: 'credit', 'debit', 'escrow', 'release'.
        currency: ISO 4217 code.
    """
    from apps.audit_logs.services.audit import AuditService
    from apps.audit_logs.models import EventType, EventCategory

    AuditService.log(
        event_type=EventType.LEDGER_ENTRY_CREATED,
        event_category=EventCategory.TRANSACTIONS,
        action=f"Ledger entry posted: type={entry_type} amount={amount} {currency} wallet={wallet_id}",
        actor=actor,
        resource_type="WalletLedgerEntry",
        resource_id=entry_id,
        request=request,
        new_values={
            "wallet_id": wallet_id, "amount": amount,
            "currency": currency, "type": entry_type,
        },
        is_compliance=True,
        retention_days=-1,
    )


def log_payout_success(
    *, actor, payout_id: str, amount: str, currency: str = "NGN",
    provider: str = "", reference: str = "", request=None
) -> None:
    """Record a successful vendor payout.

    Args:
        actor: The vendor receiving the payout.
        payout_id: VendorPayout PK.
        amount: Payout amount.
        currency: ISO 4217.
        provider: Payment gateway used.
        reference: Gateway transfer reference.
        request: Django HttpRequest.
    """
    from apps.audit_logs.services.audit import AuditService
    from apps.audit_logs.models import EventType, EventCategory

    AuditService.log(
        event_type=EventType.PAYOUT_SUCCESS,
        event_category=EventCategory.TRANSACTIONS,
        action=f"Payout success: {amount} {currency} via {provider} ref={reference}",
        actor=actor,
        actor_role="vendor",
        resource_type="VendorPayout",
        resource_id=payout_id,
        request=request,
        new_values={"amount": amount, "currency": currency, "provider": provider, "reference": reference},
        is_compliance=True,
        retention_days=-1,
    )


def log_payout_failed(
    *, actor, payout_id: str, amount: str, error: str = "", request=None
) -> None:
    """Record a failed payout attempt.

    Args:
        actor: The vendor.
        payout_id: VendorPayout PK or reference.
        amount: Attempted amount.
        error: Gateway error message.
        request: Django HttpRequest.
    """
    from apps.audit_logs.services.audit import AuditService
    from apps.audit_logs.models import EventType, EventCategory

    AuditService.log(
        event_type=EventType.PAYOUT_FAILED,
        event_category=EventCategory.TRANSACTIONS,
        action=f"Payout failed: amount={amount} error={error[:200]}",
        actor=actor,
        actor_role="vendor",
        resource_type="VendorPayout",
        resource_id=payout_id,
        request=request,
        severity="error",
        error_message=error,
        new_values={"amount": amount},
        is_compliance=True,
        retention_days=-1,
    )
