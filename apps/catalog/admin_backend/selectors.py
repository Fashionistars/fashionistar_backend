# apps/catalog/admin_backend/selectors.py
import logging
from apps.catalog.models.category import Category
from apps.catalog.models.brand import Brand
from apps.catalog.models.collection import Collections

logger = logging.getLogger(__name__)

async def aget_admin_categories():
    """
    Optimized async selector for Category list.
    """
    queryset = Category.objects.filter(is_deleted=False)
    return [category async for category in queryset.order_by("name")]

async def aget_admin_brands():
    """
    Optimized async selector for Brand list.
    """
    queryset = Brand.objects.filter(is_deleted=False)
    return [brand async for brand in queryset.order_by("name")]

async def aget_admin_collections():
    """
    Optimized async selector for Collections list.
    """
    queryset = Collections.objects.filter(is_deleted=False)
    return [collection async for collection in queryset.order_by("name")]
