# apps/audit_logs/admin_backend/selectors.py
from __future__ import annotations
import logging
from typing import Optional, Dict, Any, List
from django.db.models import Q, QuerySet
from apps.audit_logs.models import AuditEventLog

logger = logging.getLogger(__name__)

class AdminAuditSelector:
    @staticmethod
    def get_audit_logs_queryset(filters: Optional[Dict[str, Any]] = None) -> QuerySet[AuditEventLog]:
        """
        Builds optimized query for AuditEventLog.
        """
        queryset = AuditEventLog.objects.select_related("actor").all()
        if not filters:
            return queryset
            
        category = filters.get("category")
        if category:
            queryset = queryset.filter(event_category=category)
            
        severity = filters.get("severity")
        if severity:
            queryset = queryset.filter(severity=severity)
            
        search = filters.get("search")
        if search:
            queryset = queryset.filter(
                Q(action__icontains=search) |
                Q(actor_email__icontains=search) |
                Q(event_type__icontains=search)
            )
            
        return queryset

    @classmethod
    async def aget_audit_logs_list(cls, filters: Optional[Dict[str, Any]] = None) -> List[AuditEventLog]:
        """
        Asynchronously fetches audit logs list.
        """
        qs = cls.get_audit_logs_queryset(filters)
        return [log async for log in qs]

    @classmethod
    async def aget_audit_log_detail(cls, log_id: str) -> AuditEventLog:
        """
        Asynchronously retrieves detailed audit log.
        """
        return await AuditEventLog.objects.select_related("actor").aget(id=log_id)
