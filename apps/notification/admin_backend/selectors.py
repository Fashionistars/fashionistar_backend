# apps/notification/admin_backend/selectors.py
from __future__ import annotations
import logging
from typing import Optional, Dict, Any, List
from django.db.models import Q, QuerySet
from apps.notification.models.notification import Notification

logger = logging.getLogger(__name__)

class AdminNotificationSelector:
    @staticmethod
    def get_notifications_queryset(filters: Optional[Dict[str, Any]] = None) -> QuerySet[Notification]:
        """
        Builds optimized query for Notification.
        """
        queryset = Notification.objects.select_related("recipient").filter(is_deleted=False)
        if not filters:
            return queryset
            
        notification_type = filters.get("notification_type")
        if notification_type:
            queryset = queryset.filter(notification_type=notification_type)
            
        channel = filters.get("channel")
        if channel:
            queryset = queryset.filter(channel=channel)
            
        search = filters.get("search")
        if search:
            queryset = queryset.filter(
                Q(title__icontains=search) |
                Q(body__icontains=search) |
                Q(recipient__email__icontains=search)
            )
            
        return queryset

    @classmethod
    async def aget_notifications_list(cls, filters: Optional[Dict[str, Any]] = None) -> List[Notification]:
        """
        Asynchronously fetches notifications list.
        """
        qs = cls.get_notifications_queryset(filters)
        return [notification async for notification in qs]

    @classmethod
    async def aget_notification_detail(cls, notification_id: str) -> Notification:
        """
        Asynchronously retrieves detailed notification.
        """
        return await Notification.objects.select_related("recipient").aget(id=notification_id, is_deleted=False)
