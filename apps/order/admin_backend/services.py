# apps/order/admin_backend/services.py
import logging
from django.db import transaction
from apps.order.services.order_service import (
    transition_status as core_transition_status,
    release_escrow as core_release_escrow,
    cancel_order as core_cancel_order,
)
from apps.order.models.order import Order

logger = logging.getLogger(__name__)

@transaction.atomic
def admin_transition_order_status(*, order: Order, new_status: str, actor=None, note: str = "", request=None) -> Order:
    """
    Guarded status transition service wrapper for admin-only flow.
    Wraps the core service in transaction.atomic and ensures correct signature.
    """
    logger.info("Admin transitioning order %s status to %s", order.order_number, new_status)
    return core_transition_status(order=order, new_status=new_status, actor=actor, note=note, request=request)

@transaction.atomic
def admin_release_escrow(*, order: Order, actor=None, request=None) -> Order:
    """
    Guarded escrow release service wrapper for admin-only flow.
    """
    logger.info("Admin releasing escrow for order %s", order.order_number)
    return core_release_escrow(order=order, actor=actor, request=request)

@transaction.atomic
def admin_cancel_order(*, order: Order, actor=None, reason: str = "", request=None) -> Order:
    """
    Guarded order cancellation service wrapper for admin-only flow.
    """
    logger.info("Admin cancelling order %s", order.order_number)
    return core_cancel_order(order=order, actor=actor, reason=reason, request=request)
