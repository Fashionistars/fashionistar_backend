# apps/payment/admin_backend/selectors.py
from __future__ import annotations
import logging
from typing import Optional, Dict, Any, List
from django.db.models import Q, QuerySet
from apps.payment.models import PaymentIntent

logger = logging.getLogger(__name__)

class AdminPaymentSelector:
    @staticmethod
    def get_payments_queryset(filters: Optional[Dict[str, Any]] = None) -> QuerySet[PaymentIntent]:
        """
        Builds optimized query for PaymentIntent.
        """
        queryset = PaymentIntent.objects.select_related("user").all()
        if not filters:
            return queryset
            
        status = filters.get("status")
        if status:
            queryset = queryset.filter(status=status)
            
        purpose = filters.get("purpose")
        if purpose:
            queryset = queryset.filter(purpose=purpose)
            
        search = filters.get("search")
        if search:
            queryset = queryset.filter(
                Q(reference__icontains=search) |
                Q(provider_reference__icontains=search) |
                Q(user__email__icontains=search)
            )
            
        return queryset

    @classmethod
    async def aget_payments_list(cls, filters: Optional[Dict[str, Any]] = None) -> List[PaymentIntent]:
        """
        Asynchronously fetches payments list.
        """
        qs = cls.get_payments_queryset(filters)
        return [payment async for payment in qs]

    @classmethod
    async def aget_payment_detail(cls, payment_intent_id: str) -> PaymentIntent:
        """
        Asynchronously retrieves detailed payment intent.
        """
        return await PaymentIntent.objects.select_related("user").aget(id=payment_intent_id)
