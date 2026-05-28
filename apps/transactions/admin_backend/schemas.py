# apps/transactions/admin_backend/schemas.py
from datetime import datetime
from decimal import Decimal
from uuid import UUID
from typing import Optional
from ninja import Schema

class AdminTxnUserOut(Schema):
    id: int
    email: str

class AdminTxnVendorOut(Schema):
    id: UUID
    store_name: str = ""

class AdminTransactionOut(Schema):
    model_config = {"from_attributes": True}
    id: UUID
    reference: str = ""
    type: str = ""
    direction: str = ""
    status: str = ""
    amount: Decimal
    currency: str = "NGN"
    created_at: datetime
    updated_at: datetime
    user: Optional[AdminTxnUserOut] = None
    vendor: Optional[AdminTxnVendorOut] = None

