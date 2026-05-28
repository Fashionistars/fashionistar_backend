# apps/custom_order/admin_backend/schemas.py
from __future__ import annotations
from datetime import datetime
from decimal import Decimal
from uuid import UUID
from typing import List, Optional
from ninja import Schema

class AdminMilestoneSchema(Schema):
    id: UUID
    milestone_pct: int = 0
    amount_ngn: Decimal = Decimal("0.00")
    payment_status: str = "pending"
    paid_at: Optional[datetime] = None
    transaction_ref: str = ""
    payment_reference: str = ""

class AdminCustomOrderListSchema(Schema):
    id: UUID
    reference: str = ""
    client_email: str = ""
    vendor_store_name: str = ""
    budget_ngn: Decimal = Decimal("0.00")
    agreed_amount_ngn: Decimal = Decimal("0.00")
    status: str = "pending"
    created_at: datetime

    @staticmethod
    def resolve_client_email(obj):
        return obj.client.email if obj.client else ""

    @staticmethod
    def resolve_vendor_store_name(obj):
        return obj.vendor.store_name if obj.vendor else ""

class AdminCustomOrderDetailSchema(Schema):
    id: UUID
    reference: str = ""
    client_email: str = ""
    vendor_store_name: str = ""
    design_brief: str = ""
    reference_images: List[str] = []
    product_snapshot_id: Optional[UUID] = None
    order_snapshot_id: Optional[UUID] = None
    budget_ngn: Decimal = Decimal("0.00")
    agreed_amount_ngn: Decimal = Decimal("0.00")
    currency: str = "NGN"
    status: str = "pending"
    vendor_approval_note: str = ""
    approved_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: datetime
    milestones: List[AdminMilestoneSchema] = []

    @staticmethod
    def resolve_client_email(obj):
        return obj.client.email if obj.client else ""

    @staticmethod
    def resolve_vendor_store_name(obj):
        return obj.vendor.store_name if obj.vendor else ""

    @staticmethod
    def resolve_milestones(obj):
        return list(obj.milestones.all())

