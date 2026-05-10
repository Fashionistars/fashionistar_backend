"""Wallet domain audit helper — Wave B3.

Typed audit recording for wallet lifecycle events:
top-up, withdrawal, escrow hold/release, creation.
All permanent financial compliance events.
"""
from __future__ import annotations


def log_wallet_created(*, actor, wallet_id: str, currency: str = "NGN", request=None) -> None:
    """Record wallet creation.

    Args:
        actor: The user whose wallet was created.
        wallet_id: Wallet PK as string.
        currency: ISO 4217 code.
        request: Django HttpRequest.
    """
    from apps.audit_logs.services.audit import AuditService
    from apps.audit_logs.models import EventType, EventCategory

    AuditService.log(
        event_type=EventType.WALLET_CREATED,
        event_category=EventCategory.WALLET,
        action=f"Wallet created for {getattr(actor, 'email', str(actor))} currency={currency}",
        actor=actor,
        actor_role=getattr(actor, "user_type", None),
        resource_type="Wallet",
        resource_id=wallet_id,
        request=request,
        is_compliance=True,
        retention_days=-1,
    )


def log_wallet_topup(
    *, actor, wallet_id: str, amount: str, currency: str = "NGN",
    reference: str = "", request=None
) -> None:
    """Record a wallet top-up.

    Args:
        actor: The user topping up.
        wallet_id: Wallet PK.
        amount: Top-up amount as string.
        currency: ISO 4217 code.
        reference: Payment reference for this top-up.
        request: Django HttpRequest.
    """
    from apps.audit_logs.services.audit import AuditService
    from apps.audit_logs.models import EventType, EventCategory

    AuditService.log(
        event_type=EventType.WALLET_TOPUP,
        event_category=EventCategory.WALLET,
        action=f"Wallet top-up: +{amount} {currency} ref={reference}",
        actor=actor,
        actor_role=getattr(actor, "user_type", None),
        resource_type="Wallet",
        resource_id=wallet_id,
        request=request,
        new_values={"amount": amount, "currency": currency, "reference": reference},
        is_compliance=True,
        retention_days=-1,
    )


def log_wallet_withdrawal(
    *, actor, wallet_id: str, amount: str, currency: str = "NGN",
    reference: str = "", request=None
) -> None:
    """Record a wallet withdrawal / payout debit.

    Args:
        actor: The user withdrawing.
        wallet_id: Wallet PK.
        amount: Withdrawal amount as string.
        currency: ISO 4217 code.
        reference: Payout reference.
        request: Django HttpRequest.
    """
    from apps.audit_logs.services.audit import AuditService
    from apps.audit_logs.models import EventType, EventCategory

    AuditService.log(
        event_type=EventType.WALLET_WITHDRAWAL,
        event_category=EventCategory.WALLET,
        action=f"Wallet withdrawal: -{amount} {currency} ref={reference}",
        actor=actor,
        actor_role=getattr(actor, "user_type", None),
        resource_type="Wallet",
        resource_id=wallet_id,
        request=request,
        severity="warning",
        new_values={"amount": amount, "currency": currency, "reference": reference},
        is_compliance=True,
        retention_days=-1,
    )


def log_escrow_hold(
    *, actor, wallet_id: str, amount: str, order_id: str = "", request=None
) -> None:
    """Record an escrow hold on a wallet.

    Args:
        actor: The user whose wallet is being held.
        wallet_id: Wallet PK.
        amount: Escrow amount as string.
        order_id: Associated order PK.
        request: Django HttpRequest.
    """
    from apps.audit_logs.services.audit import AuditService
    from apps.audit_logs.models import EventType, EventCategory

    AuditService.log(
        event_type=EventType.WALLET_ESCROW_HOLD,
        event_category=EventCategory.WALLET,
        action=f"Escrow hold: {amount} NGN for order={order_id}",
        actor=actor,
        resource_type="Wallet",
        resource_id=wallet_id,
        request=request,
        new_values={"amount": amount, "order_id": order_id},
        is_compliance=True,
        retention_days=-1,
    )


def log_escrow_release(
    *, actor, wallet_id: str, amount: str, order_id: str = "", request=None
) -> None:
    """Record an escrow release from a wallet.

    Args:
        actor: The admin or system releasing escrow.
        wallet_id: Wallet PK.
        amount: Released amount as string.
        order_id: Associated order PK.
        request: Django HttpRequest.
    """
    from apps.audit_logs.services.audit import AuditService
    from apps.audit_logs.models import EventType, EventCategory

    AuditService.log(
        event_type=EventType.WALLET_ESCROW_RELEASE,
        event_category=EventCategory.WALLET,
        action=f"Escrow released: {amount} NGN for order={order_id}",
        actor=actor,
        resource_type="Wallet",
        resource_id=wallet_id,
        request=request,
        new_values={"amount": amount, "order_id": order_id},
        is_compliance=True,
        retention_days=-1,
    )
