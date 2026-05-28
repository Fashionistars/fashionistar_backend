# apps/product/admin_backend/schemas.py
from datetime import datetime
from decimal import Decimal
from uuid import UUID
from typing import Optional
from ninja import Schema

class AdminProductOut(Schema):
    model_config = {"from_attributes": True}
    id: UUID
    title: str
    slug: str = ""
    sku: str = ""
    price: Decimal
    currency: str = "NGN"
    stock_qty: int = 0
    in_stock: bool = False
    status: str = "draft"
    featured: bool = False
    views: int = 0
    review_count: int = 0
    rating: Decimal = Decimal("0.00")
    created_at: datetime

class AdminInventoryLogOut(Schema):
    model_config = {"from_attributes": True}
    id: UUID
    quantity_delta: int
    quantity_before: int
    quantity_after: int
    reason: str = ""
    reference_id: Optional[str] = ""
    note: str = ""
    created_at: datetime

