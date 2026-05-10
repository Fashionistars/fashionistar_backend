"""Order domain audit helper — Wave B4."""
from __future__ import annotations


def log_order_created(*, actor, order_id: str, request=None, metadata: dict | None = None) -> None:
    """Record an order creation.

    Args:
        actor: The client user placing the order.
        order_id: Order PK as string.
        request: Django HttpRequest.
        metadata: Additional context (items count, total, etc.).
    """
    from apps.audit_logs.services.audit import AuditService
    from apps.audit_logs.models import EventType, EventCategory

    AuditService.log(
        event_type=EventType.ORDER_CREATED,
        event_category=EventCategory.ORDER,
        action=f"Order created: {order_id}",
        actor=actor,
        actor_role=getattr(actor, "user_type", None),
        resource_type="Order",
        resource_id=order_id,
        request=request,
        metadata=metadata,
        is_compliance=True,
        retention_days=-1,
    )


def log_order_updated(*, actor, order_id: str, old_values: dict | None = None, new_values: dict | None = None, request=None) -> None:
    """Record an order update.

    Args:
        actor: The user updating the order.
        order_id: Order PK.
        old_values: Previous state.
        new_values: Updated state.
        request: Django HttpRequest.
    """
    from apps.audit_logs.services.audit import AuditService
    from apps.audit_logs.models import EventType, EventCategory

    AuditService.log(
        event_type=EventType.ORDER_UPDATED,
        event_category=EventCategory.ORDER,
        action=f"Order updated: {order_id}",
        actor=actor,
        actor_role=getattr(actor, "user_type", None),
        resource_type="Order",
        resource_id=order_id,
        request=request,
        old_values=old_values,
        new_values=new_values,
        is_compliance=True,
        retention_days=-1,
    )


def log_order_cancelled(*, actor, order_id: str, reason: str = "", request=None) -> None:
    """Record an order cancellation.

    Args:
        actor: The user cancelling.
        order_id: Order PK.
        reason: Cancellation reason.
        request: Django HttpRequest.
    """
    from apps.audit_logs.services.audit import AuditService
    from apps.audit_logs.models import EventType, EventCategory

    AuditService.log(
        event_type=EventType.ORDER_CANCELLED,
        event_category=EventCategory.ORDER,
        action=f"Order cancelled: {order_id} reason={reason}",
        actor=actor,
        actor_role=getattr(actor, "user_type", None),
        resource_type="Order",
        resource_id=order_id,
        request=request,
        severity="warning",
        new_values={"reason": reason},
        is_compliance=True,
        retention_days=-1,
    )


def log_order_fulfilled(*, actor, order_id: str, request=None) -> None:
    """Record an order fulfilment.

    Args:
        actor: Staff or system marking the order fulfilled.
        order_id: Order PK.
        request: Django HttpRequest.
    """
    from apps.audit_logs.services.audit import AuditService
    from apps.audit_logs.models import EventType, EventCategory

    AuditService.log(
        event_type=EventType.ORDER_FULFILLED,
        event_category=EventCategory.ORDER,
        action=f"Order fulfilled: {order_id}",
        actor=actor,
        resource_type="Order",
        resource_id=order_id,
        request=request,
        is_compliance=True,
        retention_days=-1,
    )


def log_order_returned(*, actor, order_id: str, reason: str = "", request=None) -> None:
    """Record an order return.

    Args:
        actor: The user requesting the return.
        order_id: Order PK.
        reason: Return reason.
        request: Django HttpRequest.
    """
    from apps.audit_logs.services.audit import AuditService
    from apps.audit_logs.models import EventType, EventCategory

    AuditService.log(
        event_type=EventType.ORDER_RETURNED,
        event_category=EventCategory.ORDER,
        action=f"Order returned: {order_id} reason={reason}",
        actor=actor,
        resource_type="Order",
        resource_id=order_id,
        request=request,
        new_values={"reason": reason},
        is_compliance=True,
        retention_days=-1,
    )
