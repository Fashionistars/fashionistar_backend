# apps/support/admin_backend/selectors.py
from __future__ import annotations
import logging
from typing import Optional, Dict, Any, List
from django.db.models import Q, QuerySet
from apps.support.models.support_ticket import SupportTicket

logger = logging.getLogger(__name__)

class AdminSupportSelector:
    @staticmethod
    def get_tickets_queryset(filters: Optional[Dict[str, Any]] = None) -> QuerySet[SupportTicket]:
        """
        Builds optimized query for SupportTicket.
        """
        queryset = SupportTicket.objects.select_related("submitter", "assigned_to").prefetch_related("messages")
        if not filters:
            return queryset
            
        status = filters.get("status")
        if status:
            queryset = queryset.filter(status=status)
            
        category = filters.get("category")
        if category:
            queryset = queryset.filter(category=category)
            
        search = filters.get("search")
        if search:
            queryset = queryset.filter(
                Q(title__icontains=search) |
                Q(description__icontains=search) |
                Q(submitter__email__icontains=search)
            )
            
        return queryset

    @classmethod
    async def aget_tickets_list(cls, filters: Optional[Dict[str, Any]] = None) -> List[SupportTicket]:
        """
        Asynchronously fetches tickets list.
        """
        qs = cls.get_tickets_queryset(filters)
        return [ticket async for ticket in qs]

    @classmethod
    async def aget_ticket_detail(cls, ticket_id: str) -> SupportTicket:
        """
        Asynchronously retrieves detailed ticket.
        """
        return await SupportTicket.objects.select_related("submitter", "assigned_to").prefetch_related("messages__author").aget(id=ticket_id)
