# apps/cart/admin_backend/schemas.py
from __future__ import annotations
from datetime import datetime
from decimal import Decimal
from typing import List, Optional
from ninja import Schema

class AdminCartItemSchema(Schema):
    id: str
    product_title: str
    product_price: Decimal
    variant_name: Optional[str] = None
    quantity: int
    unit_price: Decimal
    line_total: Decimal

    @staticmethod
    def resolve_product_title(obj):
        return obj.product.title if obj.product else ""

    @staticmethod
    def resolve_product_price(obj):
        return obj.product.price if obj.product else Decimal("0.00")

    @staticmethod
    def resolve_variant_name(obj):
        return str(obj.variant) if obj.variant else None

    @staticmethod
    def resolve_line_total(obj):
        return obj.line_total

class AdminCartSchema(Schema):
    id: str
    owner_email: Optional[str] = None
    session_key: Optional[str] = None
    coupon_code: Optional[str] = None
    coupon_discount: Decimal
    subtotal: Decimal
    total: Decimal
    last_activity: datetime
    items: List[AdminCartItemSchema]

    @staticmethod
    def resolve_owner_email(obj):
        return obj.user.email if obj.user else None

    @staticmethod
    def resolve_coupon_code(obj):
        return obj.coupon.code if obj.coupon else None

    @staticmethod
    def resolve_subtotal(obj):
        return obj.subtotal

    @staticmethod
    def resolve_total(obj):
        return obj.total

    @staticmethod
    def resolve_items(obj):
        return list(obj.items.all())
