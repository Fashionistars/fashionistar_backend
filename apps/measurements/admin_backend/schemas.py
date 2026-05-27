# apps/measurements/admin_backend/schemas.py
from __future__ import annotations
from datetime import datetime
from decimal import Decimal
from typing import Optional
from ninja import Schema

class AdminMeasurementProfileSchema(Schema):
    id: str
    owner_email: str
    name: str
    is_default: bool
    unit: str
    bust: Optional[Decimal] = None
    waist: Optional[Decimal] = None
    hips: Optional[Decimal] = None
    shoulder_width: Optional[Decimal] = None
    neck: Optional[Decimal] = None
    inseam: Optional[Decimal] = None
    thigh: Optional[Decimal] = None
    knee: Optional[Decimal] = None
    ankle: Optional[Decimal] = None
    arm_length: Optional[Decimal] = None
    bicep: Optional[Decimal] = None
    wrist: Optional[Decimal] = None
    height: Optional[Decimal] = None
    weight_kg: Optional[Decimal] = None
    is_verified: bool
    verified_by_email: Optional[str] = None
    notes: str
    created_at: datetime
    updated_at: datetime

    @staticmethod
    def resolve_owner_email(obj):
        return obj.owner.email if obj.owner else ""

    @staticmethod
    def resolve_verified_by_email(obj):
        return obj.verified_by.email if obj.verified_by else None
