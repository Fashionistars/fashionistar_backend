# apps/product/admin_backend/selectors.py
import logging
from django.db.models import Q
from apps.product.models import Product, ProductInventoryLog

logger = logging.getLogger(__name__)

async def aget_admin_products(search_query: str = None, status: str = None, category_slug: str = None):
    """
    Optimized async selector for admin product management.
    Performs N+1 query safety with select_related on vendor profiles.
    Queries only the primary model (Product) and traverses relationships.
    """
    queryset = Product.objects.select_related("vendor").prefetch_related("categories")
    
    if search_query:
        # SKU lives on ProductVariantGalleryMedia (reverse FK), not Product.
        # .distinct() is required because the JOIN can return multiple rows per product.
        queryset = queryset.filter(
            Q(title__icontains=search_query) |
            Q(product_variants_gallery_media__sku__iexact=search_query) |
            Q(vendor__store_name__icontains=search_query)
        ).distinct()
        
    if status:
        queryset = queryset.filter(status=status)
        
    if category_slug:
        queryset = queryset.filter(categories__slug=category_slug)
        
    return [product async for product in queryset.order_by("-created_at")[:100]]

async def aget_admin_inventory_logs(product_id: str = None):
    """
    Optimized async selector for inventory change history logs.
    """
    queryset = ProductInventoryLog.objects.select_related("product")
    if product_id:
        queryset = queryset.filter(product_id=product_id)
    return [log async for log in queryset.order_by("-created_at")[:50]]
