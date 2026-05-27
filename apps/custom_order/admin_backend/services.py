# apps/custom_order/admin_backend/services.py
from __future__ import annotations
import logging
from django.db import transaction
from django.utils import timezone
from apps.common.events import event_bus
from apps.custom_order.models import CustomOrder, CustomOrderStatus

logger = logging.getLogger(__name__)

@transaction.atomic
def admin_update_custom_order_status(
    custom_order_id: str,
    status: str,
    admin_user,
    reason: str = "",
) -> CustomOrder:
    """
    Admin-only service to update a custom order status with event logging.
    """
    order = CustomOrder.objects.select_for_update().get(id=custom_order_id)
    old_status = order.status
    if old_status == status:
        return order
        
    order.status = status
    if status == CustomOrderStatus.COMPLETED:
        order.completed_at = timezone.now()
    elif status == CustomOrderStatus.APPROVED:
        order.approved_at = timezone.now()
        
    order.save()
    logger.info("Admin %s updated custom order %s status from %s to %s", admin_user.email, order.reference, old_status, status)
    
    event_bus.emit_on_commit(
        "admin.custom_order.status_updated",
        custom_order_id=str(order.id),
        old_status=old_status,
        new_status=status,
        admin_id=str(admin_user.id),
        reason=reason,
    )
    return order
