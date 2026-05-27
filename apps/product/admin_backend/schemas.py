# apps/product/admin_backend/schemas.py
from datetime import datetime
from decimal import Decimal
from ninja import Schema

class AdminProductOut(Schema):
    model_config = {"from_attributes": True}
    id: str
    title: str
    slug: str
    sku: str
    price: Decimal
    currency: str = "NGN"
    stock_qty: int
    in_stock: bool
    status: str
    featured: bool
    views: int
    review_count: int
    rating: Decimal
    created_at: datetime

class AdminInventoryLogOut(Schema):
    model_config = {"from_attributes": True}
    id: str
    quantity_delta: int
    quantity_before: int
    quantity_after: int
    reason: str
    reference_id: str = ""
    note: str = ""
    created_at: datetime
