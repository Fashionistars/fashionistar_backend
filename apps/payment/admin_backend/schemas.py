# apps/payment/admin_backend/schemas.py
from __future__ import annotations
from datetime import datetime
from decimal import Decimal
from typing import Optional, Dict, Any
from ninja import Schema

class AdminPaymentSchema(Schema):
    id: str
    owner_email: str
    provider: str
    purpose: str
    amount: Decimal
    currency: str
    status: str
    reference: str
    provider_reference: str
    order_id: str
    measurement_request_id: str
    created_at: datetime
    updated_at: datetime
    metadata: Dict[str, Any]

    @staticmethod
    def resolve_owner_email(obj):
        return obj.user.email if obj.user else ""
