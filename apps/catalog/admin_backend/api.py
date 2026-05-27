# apps/catalog/admin_backend/api.py
import logging
from typing import List
from ninja import Router

from apps.admin_backend.permissions import admin_auth
from apps.catalog.admin_backend.selectors import (
    aget_admin_categories,
    aget_admin_brands,
    aget_admin_collections,
)
from apps.catalog.admin_backend.schemas import (
    AdminCategoryOut,
    AdminBrandOut,
    AdminCollectionOut,
)

logger = logging.getLogger(__name__)

router = Router(tags=["Admin - Catalog"])

@router.get("/categories/", response=List[AdminCategoryOut], auth=admin_auth)
async def list_categories(request):
    """
    Async read endpoint for catalog categories.
    """
    return await aget_admin_categories()

@router.get("/brands/", response=List[AdminBrandOut], auth=admin_auth)
async def list_brands(request):
    """
    Async read endpoint for catalog brands.
    """
    return await aget_admin_brands()

@router.get("/collections/", response=List[AdminCollectionOut], auth=admin_auth)
async def list_collections(request):
    """
    Async read endpoint for catalog collections.
    """
    return await aget_admin_collections()

