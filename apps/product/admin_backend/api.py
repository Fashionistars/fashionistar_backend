# apps/product/admin_backend/api.py
import logging
from typing import List, Optional
from ninja import Router

from apps.admin_backend.permissions import admin_auth
from apps.product.admin_backend.selectors import aget_admin_products, aget_admin_inventory_logs
from apps.product.admin_backend.schemas import AdminProductOut, AdminInventoryLogOut

logger = logging.getLogger(__name__)

router = Router(tags=["Admin - Product"])

@router.get("/", response=List[AdminProductOut], auth=admin_auth)
async def list_products(
    request,
    search: Optional[str] = None,
    status: Optional[str] = None,
    category_slug: Optional[str] = None
):
    """
    Async read endpoint for admin products.
    """
    return await aget_admin_products(search_query=search, status=status, category_slug=category_slug)

@router.get("/inventory-logs/", response=List[AdminInventoryLogOut], auth=admin_auth)
async def list_inventory_logs(request, product_id: Optional[str] = None):
    """
    Async read endpoint for product inventory changes.
    """
    return await aget_admin_inventory_logs(product_id=product_id)

