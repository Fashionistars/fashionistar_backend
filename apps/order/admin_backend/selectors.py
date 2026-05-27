# apps/order/admin_backend/selectors.py
import logging
from apps.order.models.order import Order

logger = logging.getLogger(__name__)

async def aget_admin_orders(search_query: str = None, status: str = None):
    """
    Optimized async selector for admin order lists.
    Avoids N+1 query loops by selecting user and vendor profiles up-front.
    """
    queryset = Order.objects.select_related("user", "vendor")
    
    if search_query:
        from django.db.models import Q
        queryset = queryset.filter(
            Q(order_number__icontains=search_query) |
            Q(user__email__icontains=search_query) |
            Q(vendor__store_name__icontains=search_query)
        )
        
    if status:
        queryset = queryset.filter(status=status)
        
    return [order async for order in queryset.order_by("-created_at")[:100]]

async def aget_admin_order_detail(order_id: str):
    """
    Retrieve details for a single order including prefetch of related items.
    """
    try:
        return await Order.objects.select_related("user", "vendor").prefetch_related("cart_order_items").aget(id=order_id)
    except Order.DoesNotExist:
        return None
