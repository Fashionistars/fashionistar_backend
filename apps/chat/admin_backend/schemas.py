# apps/chat/admin_backend/schemas.py
from __future__ import annotations
from datetime import datetime
from uuid import UUID
from typing import List, Optional
from ninja import Schema

class AdminChatMessageSchema(Schema):
    id: UUID
    author_email: str = ""
    content: str = ""
    created_at: datetime

    @staticmethod
    def resolve_author_email(obj):
        return obj.author.email if obj.author else ""

class AdminConversationSchema(Schema):
    id: UUID
    buyer_email: str = ""
    vendor_email: str = ""
    status: str = "active"
    created_at: datetime
    updated_at: datetime
    messages: List[AdminChatMessageSchema] = []

    @staticmethod
    def resolve_buyer_email(obj):
        return obj.buyer.email if obj.buyer else ""

    @staticmethod
    def resolve_vendor_email(obj):
        return obj.vendor.email if obj.vendor else ""

    @staticmethod
    def resolve_messages(obj):
        return list(obj.messages.all()[:50])

class AdminChatEscalationSchema(Schema):
    id: UUID
    conversation_id: Optional[str] = None
    buyer_email: str = ""
    vendor_email: str = ""
    reason: str = ""
    status: str = "open"
    resolution_notes: Optional[str] = None
    resolved_at: Optional[datetime] = None
    assigned_admin_email: Optional[str] = None
    created_at: datetime

    @staticmethod
    def resolve_conversation_id(obj):
        return str(obj.conversation.id) if obj.conversation else ""

    @staticmethod
    def resolve_buyer_email(obj):
        return obj.conversation.buyer.email if obj.conversation and obj.conversation.buyer else ""

    @staticmethod
    def resolve_vendor_email(obj):
        return obj.conversation.vendor.email if obj.conversation and obj.conversation.vendor else ""

    @staticmethod
    def resolve_assigned_admin_email(obj):
        return obj.assigned_admin.email if obj.assigned_admin else None

