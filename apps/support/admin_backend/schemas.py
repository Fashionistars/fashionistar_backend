# apps/support/admin_backend/schemas.py
from __future__ import annotations
from datetime import datetime
from uuid import UUID
from typing import List, Optional, Dict, Any
from ninja import Schema

class AdminTicketMessageSchema(Schema):
    id: UUID
    author_email: Optional[str] = None
    body: str = ""
    is_staff_reply: bool = False
    attachments: List[str] = []
    created_at: datetime

    @staticmethod
    def resolve_author_email(obj):
        return obj.author.email if obj.author else None

class AdminSupportTicketSchema(Schema):
    id: UUID
    submitter_email: Optional[str] = None
    order_id: Optional[str] = None
    category: str = ""
    priority: str = "medium"
    status: str = "open"
    title: str = ""
    description: str = ""
    metadata: Dict[str, Any] = {}
    assigned_to_email: Optional[str] = None
    resolution_notes: str = ""
    resolved_at: Optional[datetime] = None
    closed_at: Optional[datetime] = None
    created_at: datetime
    messages: List[AdminTicketMessageSchema] = []

    @staticmethod
    def resolve_submitter_email(obj):
        return obj.submitter.email if obj.submitter else None

    @staticmethod
    def resolve_order_id(obj):
        return str(obj.order_id) if obj.order_id else None

    @staticmethod
    def resolve_assigned_to_email(obj):
        return obj.assigned_to.email if obj.assigned_to else None

    @staticmethod
    def resolve_messages(obj):
        return list(obj.messages.all())
