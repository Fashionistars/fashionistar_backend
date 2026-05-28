# apps/wallet/admin_backend/schemas.py
from datetime import datetime
from decimal import Decimal
from uuid import UUID
from typing import Optional
from ninja import Schema

class AdminWalletOwnerOut(Schema):
    id: int
    email: str
    role: str = ""

class AdminWalletOut(Schema):
    model_config = {"from_attributes": True}
    id: UUID
    owner: Optional[AdminWalletOwnerOut] = None
    owner_type: str = ""
    balance: Decimal
    ledger_balance: Decimal
    currency: str = "NGN"
    status: str = "active"
    created_at: datetime
    updated_at: datetime

class AdminWalletHoldOut(Schema):
    model_config = {"from_attributes": True}
    id: UUID
    order_id: Optional[UUID] = None
    amount: Decimal
    currency: str = "NGN"
    status: str = "active"
    reference: str = ""
    created_at: datetime

