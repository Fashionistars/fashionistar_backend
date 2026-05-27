# apps/custom_order/admin_backend/selectors.py
from __future__ import annotations
import logging
from typing import Optional, Dict, Any, List
from django.db.models import Q, QuerySet
from apps.custom_order.models import CustomOrder

logger = logging.getLogger(__name__)

class AdminCustomOrderSelector:
    @staticmethod
    def get_custom_orders_queryset(filters: Optional[Dict[str, Any]] = None) -> QuerySet[CustomOrder]:
        """
        Builds optimized queryset for CustomOrder.
        """
        queryset = CustomOrder.objects.select_related("client", "vendor__user").prefetch_related("milestones").filter(is_deleted=False)
        if not filters:
            return queryset
            
        status = filters.get("status")
        if status:
            queryset = queryset.filter(status=status)
            
        search = filters.get("search")
        if search:
            queryset = queryset.filter(
                Q(reference__icontains=search) |
                Q(client__email__icontains=search) |
                Q(vendor__store_name__icontains=search)
            )
            
        return queryset

    @classmethod
    async def aget_custom_orders_list(cls, filters: Optional[Dict[str, Any]] = None) -> List[CustomOrder]:
        """
        Asynchronously fetches custom orders list.
        """
        qs = cls.get_custom_orders_queryset(filters)
        return [order async for order in qs]

    @classmethod
    async def aget_custom_order_detail(cls, custom_order_id: str) -> CustomOrder:
        """
        Asynchronously retrieves detailed custom order.
        """
        return await CustomOrder.objects.select_related("client", "vendor__user").prefetch_related("milestones").aget(id=custom_order_id, is_deleted=False)
