"""Payment domain audit helper — Wave B2.

Typed audit recording for payment lifecycle events:
initiated, success, failed, refund, dispute.
All calls are fire-and-forget, guaranteed never to raise.
"""
from __future__ import annotations


def log_payment_initiated(
    *, actor, resource_id: str, amount: str, currency: str = "NGN",
    provider: str = "", request=None
) -> None:
    """Record a payment initiation event.

    Args:
        actor: The ``UnifiedUser`` initiating the payment.
        resource_id: PaymentTransaction reference or PK.
        amount: Decimal amount as string.
        currency: ISO 4217 code.
        provider: Gateway name (paystack, flutterwave, etc.).
        request: Django HttpRequest.
    """
    from apps.audit_logs.services.audit import AuditService
    from apps.audit_logs.models import EventType, EventCategory

    AuditService.log(
        event_type=EventType.PAYMENT_INITIATED,
        event_category=EventCategory.PAYMENT,
        action=f"Payment initiated: {amount} {currency} via {provider or 'gateway'} ref={resource_id}",
        actor=actor,
        actor_role=getattr(actor, "user_type", None),
        resource_type="PaymentTransaction",
        resource_id=resource_id,
        request=request,
        new_values={"amount": amount, "currency": currency, "provider": provider},
        is_compliance=True,
        retention_days=-1,
    )


def log_payment_success(
    *, actor, resource_id: str, amount: str, currency: str = "NGN",
    provider: str = "", gateway_reference: str = "", request=None
) -> None:
    """Record a successful payment.

    Args:
        actor: The user who paid.
        resource_id: PaymentTransaction PK or reference.
        amount: Amount as string.
        currency: ISO 4217 code.
        provider: Gateway that processed the payment.
        gateway_reference: Gateway's own transaction ID.
        request: Django HttpRequest.
    """
    from apps.audit_logs.services.audit import AuditService
    from apps.audit_logs.models import EventType, EventCategory

    AuditService.log(
        event_type=EventType.PAYMENT_SUCCESS,
        event_category=EventCategory.PAYMENT,
        action=f"Payment successful: {amount} {currency} via {provider} gateway_ref={gateway_reference}",
        actor=actor,
        actor_role=getattr(actor, "user_type", None),
        resource_type="PaymentTransaction",
        resource_id=resource_id,
        request=request,
        new_values={
            "amount": amount, "currency": currency,
            "provider": provider, "gateway_reference": gateway_reference,
        },
        is_compliance=True,
        retention_days=-1,
    )


def log_payment_failed(
    *, actor=None, resource_id: str, amount: str, currency: str = "NGN",
    provider: str = "", error: str = "", request=None
) -> None:
    """Record a failed payment attempt.

    Args:
        actor: The user if identified.
        resource_id: PaymentTransaction reference.
        amount: Amount as string.
        currency: ISO 4217 code.
        provider: Gateway name.
        error: Error message from the gateway.
        request: Django HttpRequest.
    """
    from apps.audit_logs.services.audit import AuditService
    from apps.audit_logs.models import EventType, EventCategory

    AuditService.log(
        event_type=EventType.PAYMENT_FAILED,
        event_category=EventCategory.PAYMENT,
        action=f"Payment failed: {amount} {currency} via {provider}: {error[:200]}",
        actor=actor,
        actor_role=getattr(actor, "user_type", None) if actor else None,
        resource_type="PaymentTransaction",
        resource_id=resource_id,
        request=request,
        severity="error",
        error_message=error,
        new_values={"amount": amount, "currency": currency, "provider": provider},
        is_compliance=True,
        retention_days=-1,
    )


def log_refund_initiated(
    *, actor, resource_id: str, amount: str, currency: str = "NGN",
    reason: str = "", request=None
) -> None:
    """Record a refund initiation.

    Args:
        actor: The admin or user initiating the refund.
        resource_id: Original PaymentTransaction PK.
        amount: Refund amount as string.
        currency: ISO 4217 code.
        reason: Reason for the refund.
        request: Django HttpRequest.
    """
    from apps.audit_logs.services.audit import AuditService
    from apps.audit_logs.models import EventType, EventCategory

    AuditService.log(
        event_type=EventType.REFUND_INITIATED,
        event_category=EventCategory.PAYMENT,
        action=f"Refund initiated: {amount} {currency} for tx={resource_id} reason={reason}",
        actor=actor,
        resource_type="PaymentTransaction",
        resource_id=resource_id,
        request=request,
        severity="warning",
        new_values={"amount": amount, "currency": currency, "reason": reason},
        is_compliance=True,
        retention_days=-1,
    )


def log_refund_completed(
    *, actor, resource_id: str, amount: str, currency: str = "NGN", request=None
) -> None:
    """Record a completed refund.

    Args:
        actor: The actor who completed the refund.
        resource_id: PaymentTransaction PK.
        amount: Refunded amount.
        currency: ISO 4217 code.
        request: Django HttpRequest.
    """
    from apps.audit_logs.services.audit import AuditService
    from apps.audit_logs.models import EventType, EventCategory

    AuditService.log(
        event_type=EventType.REFUND_COMPLETED,
        event_category=EventCategory.PAYMENT,
        action=f"Refund completed: {amount} {currency} for tx={resource_id}",
        actor=actor,
        resource_type="PaymentTransaction",
        resource_id=resource_id,
        request=request,
        new_values={"amount": amount, "currency": currency},
        is_compliance=True,
        retention_days=-1,
    )


def log_dispute_opened(
    *, actor, resource_id: str, reason: str = "", request=None
) -> None:
    """Record a payment dispute being opened.

    Args:
        actor: The user opening the dispute.
        resource_id: PaymentTransaction PK.
        reason: Dispute reason text.
        request: Django HttpRequest.
    """
    from apps.audit_logs.services.audit import AuditService
    from apps.audit_logs.models import EventType, EventCategory

    AuditService.log(
        event_type=EventType.DISPUTE_OPENED,
        event_category=EventCategory.PAYMENT,
        action=f"Dispute opened for tx={resource_id}: {reason}",
        actor=actor,
        resource_type="PaymentTransaction",
        resource_id=resource_id,
        request=request,
        severity="warning",
        is_compliance=True,
        retention_days=-1,
    )
