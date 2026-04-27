# apps/order/selectors/order_selectors.py
"""
Read-only querysets for the Order domain.
"""

from django.db.models import Q

from apps.order.models import Order, OrderStatus


def get_user_orders(user_id):
    return (
        Order.objects.filter(user_id=user_id)
        .prefetch_related("items__product", "items__variant", "status_history")
        .select_related("vendor", "courier")
        .order_by("-created_at")
    )


def get_vendor_orders(vendor_id, status=None):
    qs = (
        Order.objects.filter(vendor_id=vendor_id)
        .prefetch_related("items", "status_history")
        .select_related("courier")
        .order_by("-created_at")
    )
    if status:
        qs = qs.filter(status=status)
    return qs


def get_order_by_id_for_user(order_id, user_id) -> Order | None:
    try:
        return (
            Order.objects.prefetch_related("items__product", "status_history")
            .get(id=order_id, user_id=user_id)
        )
    except Order.DoesNotExist:
        return None


def get_order_by_id_for_vendor(order_id, vendor_id) -> Order | None:
    try:
        return (
            Order.objects.prefetch_related("items__product", "status_history")
            .get(id=order_id, vendor_id=vendor_id)
        )
    except Order.DoesNotExist:
        return None


def get_order_by_payment_ref(payment_reference: str) -> Order | None:
    try:
        return Order.objects.get(payment_reference=payment_reference)
    except Order.DoesNotExist:
        return None


def get_admin_orders(status=None, user_id=None, vendor_id=None):
    qs = Order.objects.prefetch_related("items").select_related("user", "vendor").order_by("-created_at")
    if status:
        qs = qs.filter(status=status)
    if user_id:
        qs = qs.filter(user_id=user_id)
    if vendor_id:
        qs = qs.filter(vendor_id=vendor_id)
    return qs
