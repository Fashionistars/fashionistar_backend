# apps/custom_order/admin_backend/api.py
import logging
from typing import List, Optional
from ninja import Router

from apps.admin_backend.permissions import admin_auth
from apps.custom_order.admin_backend.selectors import AdminCustomOrderSelector
from apps.custom_order.admin_backend.schemas import AdminCustomOrderListSchema, AdminCustomOrderDetailSchema

logger = logging.getLogger(__name__)

router = Router(tags=["Admin - Custom Order"])

@router.get("/", response=List[AdminCustomOrderListSchema], auth=admin_auth)
async def list_custom_orders(
    request,
    search: Optional[str] = None,
    status: Optional[str] = None,
):
    """
    Async read endpoint for bespoke custom orders list.
    """
    filters = {}
    if search:
        filters["search"] = search
    if status:
        filters["status"] = status
    return await AdminCustomOrderSelector.aget_custom_orders_list(filters)

@router.get("/{custom_order_id}/", response=AdminCustomOrderDetailSchema, auth=admin_auth)
async def get_custom_order_detail(request, custom_order_id: str):
    """
    Async read endpoint for bespoke custom order detail.
    """
    return await AdminCustomOrderSelector.aget_custom_order_detail(custom_order_id)
