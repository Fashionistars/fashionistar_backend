# apps/cart/admin_backend/selectors.py
from __future__ import annotations
import logging
from typing import Optional, Dict, Any, List
from django.db.models import Q, QuerySet
from apps.cart.models.cart import Cart

logger = logging.getLogger(__name__)

class AdminCartSelector:
    @staticmethod
    def get_carts_queryset(filters: Optional[Dict[str, Any]] = None) -> QuerySet[Cart]:
        """
        Builds optimized query for Cart.
        """
        queryset = Cart.objects.select_related("user").prefetch_related("items__product", "items__variant").filter(is_deleted=False)
        if not filters:
            return queryset
            
        search = filters.get("search")
        if search:
            queryset = queryset.filter(
                Q(user__email__icontains=search) |
                Q(session_key__icontains=search)
            )
            
        return queryset

    @classmethod
    async def aget_carts_list(cls, filters: Optional[Dict[str, Any]] = None) -> List[Cart]:
        """
        Asynchronously fetches carts list.
        """
        qs = cls.get_carts_queryset(filters)
        return [cart async for cart in qs]

    @classmethod
    async def aget_cart_detail(cls, cart_id: str) -> Cart:
        """
        Asynchronously retrieves detailed cart.
        """
        return await Cart.objects.select_related("user").prefetch_related("items__product", "items__variant").aget(id=cart_id, is_deleted=False)
