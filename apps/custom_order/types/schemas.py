# apps/custom_order/types/schemas.py
"""
Django-Ninja Pydantic schemas for the Custom Order domain.

All schemas are strict — no extra fields allowed.
Updated: 2026-05-26
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional, List
from uuid import UUID

from ninja import Schema


# ── Output schemas ────────────────────────────────────────────────────────────

class CustomOrderMilestoneOut(Schema):
    id: UUID
    milestone_pct: int
    amount_ngn: Decimal
    payment_status: str
    paid_at: Optional[datetime] = None


class CustomOrderOut(Schema):
    id: UUID
    reference: str
    status: str
    design_brief: str
    vendor_approval_note: str
    budget_ngn: Decimal
    agreed_amount_ngn: Optional[Decimal] = None
    product_snapshot_id: Optional[str] = None
    order_snapshot_id: Optional[str] = None
    vendor_store_name: str
    created_at: datetime
    updated_at: datetime
    milestones: List[CustomOrderMilestoneOut] = []

    @staticmethod
    def from_orm_obj(obj) -> "CustomOrderOut":
        return CustomOrderOut(
            id=obj.id,
            reference=obj.reference,
            status=obj.status,
            design_brief=obj.design_brief,
            vendor_approval_note=obj.vendor_approval_note,
            budget_ngn=obj.budget_ngn,
            agreed_amount_ngn=obj.agreed_amount_ngn,
            product_snapshot_id=obj.product_snapshot_id or None,
            order_snapshot_id=obj.order_snapshot_id or None,
            vendor_store_name=getattr(obj.vendor, "store_name", ""),
            created_at=obj.created_at,
            updated_at=obj.updated_at,
            milestones=[
                CustomOrderMilestoneOut(
                    id=m.id,
                    milestone_pct=m.milestone_pct,
                    amount_ngn=m.amount_ngn,
                    payment_status=m.payment_status,
                    paid_at=m.paid_at,
                )
                for m in obj.milestones.all()
            ],
        )


# ── Input schemas ─────────────────────────────────────────────────────────────

class CustomOrderCreateIn(Schema):
    vendor_id: str
    design_brief: str
    budget_ngn: Decimal
    product_snapshot_id: Optional[str] = None
    order_snapshot_id: Optional[str] = None
    reference_images: Optional[List[str]] = None


class VendorApproveIn(Schema):
    agreed_amount_ngn: Decimal
    note: str = ""


class MilestonePayIn(Schema):
    milestone_pct: int   # 30 | 50 | 70 | 100
    payment_method: str = "wallet"
