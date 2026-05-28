# apps/notification/admin_backend/schemas.py
from __future__ import annotations
from datetime import datetime
from uuid import UUID
from typing import Optional, Dict, Any
from ninja import Schema

class AdminNotificationSchema(Schema):
    id: UUID
    recipient_email: Optional[str] = None
    notification_type: str = ""
    channel: str = ""
    title: str = ""
    body: str = ""
    metadata: Dict[str, Any] = {}
    sent_at: Optional[datetime] = None
    read_at: Optional[datetime] = None
    external_id: str = ""
    failed: bool = False
    error_msg: str = ""
    created_at: datetime

    @staticmethod
    def resolve_recipient_email(obj):
        return obj.recipient.email if obj.recipient else None

