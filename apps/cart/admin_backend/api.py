# apps/cart/admin_backend/api.py
import logging
from typing import List, Optional
from ninja import Router

from apps.admin_backend.permissions import admin_auth
from apps.cart.admin_backend.selectors import AdminCartSelector
from apps.cart.admin_backend.schemas import AdminCartSchema

logger = logging.getLogger(__name__)

router = Router(tags=["Admin - Cart"])

@router.get("/", response=List[AdminCartSchema], auth=admin_auth)
async def list_carts(
    request,
    search: Optional[str] = None,
):
    """
    Get all active shopping carts in the system.
    """
    filters = {}
    if search:
        filters["search"] = search
    return await AdminCartSelector.aget_carts_list(filters)

@router.get("/{cart_id}/", response=AdminCartSchema, auth=admin_auth)
async def get_cart_detail(request, cart_id: str):
    """
    Get detailed information about a specific shopping cart.
    """
    try:
        return await AdminCartSelector.aget_cart_detail(cart_id)
    except Exception as e:
        from ninja.errors import HttpError
        raise HttpError(404, f"Cart not found: {str(e)}")
