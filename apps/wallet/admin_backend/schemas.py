# apps/wallet/admin_backend/schemas.py
from datetime import datetime
from decimal import Decimal
from typing import Optional
from ninja import Schema

class AdminWalletOwnerOut(Schema):
    id: int
    email: str
    role: str = ""

class AdminWalletOut(Schema):
    model_config = {"from_attributes": True}
    id: str
    owner: Optional[AdminWalletOwnerOut] = None
    owner_type: str
    balance: Decimal
    ledger_balance: Decimal
    currency: str
    status: str
    created_at: datetime
    updated_at: datetime

class AdminWalletHoldOut(Schema):
    model_config = {"from_attributes": True}
    id: str
    order_id: str
    amount: Decimal
    currency: str
    status: str
    reference: str
    created_at: datetime
