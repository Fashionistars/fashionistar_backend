# apps/order/admin_backend/api.py
import logging
from typing import List, Optional
from ninja import Router
from apps.admin_backend.permissions import admin_auth
from apps.order.admin_backend.schemas import AdminOrderOut, AdminOrderDetailOut
from apps.order.admin_backend.selectors import aget_admin_orders, aget_admin_order_detail
from django.http import Http404

logger = logging.getLogger(__name__)

router = Router(tags=["Admin - Order"])

@router.get("/", response=List[AdminOrderOut], auth=admin_auth)
async def list_orders(
    request,
    search: Optional[str] = None,
    status: Optional[str] = None
):
    """
    Highly-concurrent async read endpoint to query optimized list of orders.
    Enforces N+1 query safety and selects related users/vendors.
    """
    logger.info("Admin list orders fetched. Search: %s, Status: %s", search, status)
    return await aget_admin_orders(search_query=search, status=status)

@router.get("/{order_id}/", response=AdminOrderDetailOut, auth=admin_auth)
async def get_order_detail(request, order_id: str):
    """
    Highly-concurrent async read endpoint for order details with prefetch support.
    """
    logger.info("Admin order details fetched for order: %s", order_id)
    order = await aget_admin_order_detail(order_id=order_id)
    if not order:
        raise Http404("Order not found.")
    return order
