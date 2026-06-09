# apps/client/types/client_schemas.py
"""
Pydantic / Django-Ninja schemas for the async Client API.

These replace DRF serializers for all Ninja endpoints under /api/v1/ninja/.

Production-grade 2026 schema set — fully typed, camelCase-compatible,
zero-default-explosion pattern.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from ninja import Schema
from pydantic import Field


# ── Address ─────────────────────────────────────────────────────────────────


class AddressOut(Schema):
    id:             UUID
    label:          str
    full_name:      str
    phone:          str
    street_address: str
    city:           str
    state:          str
    country:        str
    postal_code:    str
    is_default:     bool


# ── Profile ──────────────────────────────────────────────────────────────────


class ProfileOut(Schema):
    id:                          UUID
    user_id:                     str
    user_email:                  str
    bio:                         str
    default_shipping_address:    str
    preferred_size:              str
    style_preferences:           list[str]
    favourite_colours:           list[str]
    country:                     str
    state:                       str
    is_profile_complete:         bool
    total_orders:                int
    total_spent_ngn:             Decimal
    email_notifications_enabled: bool
    sms_notifications_enabled:   bool
    last_active_at:              datetime | None = None
    phone_verified:              bool = False
    loyalty_tier:                str = "standard"
    loyalty_points:              int = 0
    referral_code:               str | None = None
    referral_count:              int = 0
    body_type:                   str = ""
    occasion_preferences:        list[str] = Field(default_factory=list)
    addresses:                   list[AddressOut] = Field(default_factory=list)


# ── Measurement Snapshot ─────────────────────────────────────────────────────


class MeasurementSnapshotOut(Schema):
    id:              str | None = None
    height_cm:       float | None = None
    weight_kg:       float | None = None
    chest_cm:        float | None = None
    waist_cm:        float | None = None
    hip_cm:          float | None = None
    shoulder_cm:     float | None = None
    arm_length_cm:   float | None = None
    inseam_cm:       float | None = None
    updated_at:      datetime | None = None


# ── Analytics ────────────────────────────────────────────────────────────────


class AnalyticsOut(Schema):
    total_orders:     int
    total_spent_ngn:  float
    saved_addresses:  int
    pending_orders:   int = 0
    active_orders:    int = 0
    completed_orders: int = 0
    wishlist_count:   int = 0


# ── Dashboard ────────────────────────────────────────────────────────────────


class DashboardOut(Schema):
    profile:              ProfileOut
    analytics:            AnalyticsOut
    measurement_snapshot: MeasurementSnapshotOut = Field(default_factory=MeasurementSnapshotOut)
    ai_recommendations:   list[Any] = Field(default_factory=list)


# ── Input Schemas ─────────────────────────────────────────────────────────────


class ProfileUpdateIn(Schema):
    bio:                         str | None = None
    default_shipping_address:    str | None = None
    state:                       str | None = None
    country:                     str | None = None
    preferred_size:              str | None = None
    style_preferences:           list[str] | None = None
    favourite_colours:           list[str] | None = None
    email_notifications_enabled: bool | None = None
    sms_notifications_enabled:   bool | None = None
    body_type:                   str | None = None
    occasion_preferences:        list[str] | None = None


class AddressIn(Schema):
    label:          str = "Home"
    full_name:      str = ""
    phone:          str = ""
    street_address: str
    city:           str
    state:          str
    country:        str = "Nigeria"
    postal_code:    str = ""
    is_default:     bool = False


# ── Custom Order Schemas ──────────────────────────────────────────────────────


class CustomOrderMilestoneOut(Schema):
    id:              UUID
    milestone_pct:   int           # 30, 50, 70, 100
    amount_ngn:      Decimal
    payment_status:  str           # pending | paid | failed
    paid_at:         datetime | None = None


class CustomOrderOut(Schema):
    id:                   UUID
    reference:            str
    status:               str       # draft | submitted | approved | in_production | completed | cancelled
    design_brief:         str
    vendor_approval_note: str
    budget_ngn:           Decimal
    product_snapshot_id:  str | None = None
    order_snapshot_id:    str | None = None
    vendor_store_name:    str
    created_at:           datetime
    updated_at:           datetime
    milestones:           list[CustomOrderMilestoneOut] = Field(default_factory=list)


class CustomOrderIn(Schema):
    vendor_id:           UUID
    design_brief:        str
    budget_ngn:          Decimal
    product_snapshot_id: str | None = None
    order_snapshot_id:   str | None = None
    reference_images:    list[str] = Field(default_factory=list)   # upload URLs


class CustomOrderApproveIn(Schema):
    vendor_approval_note: str
    agreed_amount_ngn:    Decimal


class MilestonePayIn(Schema):
    milestone_pct:        int   # 30 | 50 | 70 | 100
    payment_method:       str = "wallet"   # wallet | card | bank_transfer
