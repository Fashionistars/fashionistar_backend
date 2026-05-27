# apps/chat/admin_backend/selectors.py
from __future__ import annotations
import logging
from typing import Optional, Dict, Any, List
from django.db.models import Q, QuerySet
from apps.chat.models.conversation import Conversation, ChatEscalation

logger = logging.getLogger(__name__)

class AdminChatSelector:
    @staticmethod
    def get_conversations_queryset(filters: Optional[Dict[str, Any]] = None) -> QuerySet[Conversation]:
        """
        Builds optimized query for Conversation.
        """
        queryset = Conversation.objects.select_related("buyer", "vendor").prefetch_related("messages")
        if not filters:
            return queryset
            
        status = filters.get("status")
        if status:
            queryset = queryset.filter(status=status)
            
        search = filters.get("search")
        if search:
            queryset = queryset.filter(
                Q(buyer__email__icontains=search) |
                Q(vendor__email__icontains=search)
            )
            
        return queryset

    @classmethod
    async def aget_conversations_list(cls, filters: Optional[Dict[str, Any]] = None) -> List[Conversation]:
        """
        Asynchronously fetches conversations list.
        """
        qs = cls.get_conversations_queryset(filters)
        return [conversation async for conversation in qs]

    @classmethod
    async def aget_conversation_detail(cls, conversation_id: str) -> Conversation:
        """
        Asynchronously retrieves detailed conversation.
        """
        return await Conversation.objects.select_related("buyer", "vendor").prefetch_related("messages__author").aget(id=conversation_id)

    @classmethod
    async def aget_escalations_list(cls) -> List[ChatEscalation]:
        """
        Asynchronously fetches all escalations.
        """
        qs = ChatEscalation.objects.select_related("conversation__buyer", "conversation__vendor", "assigned_admin").all()
        return [escalation async for escalation in qs]
