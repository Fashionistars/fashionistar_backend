# apps/payment/admin_backend/schemas.py
from __future__ import annotations
from datetime import datetime
from decimal import Decimal
from uuid import UUID
from typing import Optional, Dict, Any
from ninja import Schema

class AdminPaymentSchema(Schema):
    id: UUID
    owner_email: str = ""
    provider: str = ""
    purpose: str = ""
    amount: Decimal
    currency: str = "NGN"
    status: str = ""
    reference: str = ""
    provider_reference: str = ""
    order_id: Optional[UUID] = None
    measurement_request_id: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime
    metadata: Dict[str, Any] = {}

    @staticmethod
    def resolve_owner_email(obj):
        return obj.user.email if obj.user else ""

