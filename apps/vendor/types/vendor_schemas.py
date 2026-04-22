# apps/vendor/types/vendor_schemas.py
"""
Pydantic / Django-Ninja schemas for the async Vendor API.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

from ninja import Schema
from pydantic import Field


# ── Sub-schemas ────────────────────────────────────────────────────────


class SetupStateOut(Schema):
    current_step:         int
    profile_complete:     bool
    bank_details:         bool
    id_verified:          bool
    first_product:        bool
    onboarding_done:      bool
    completion_percentage: int


class AnalyticsOut(Schema):
    total_products: int
    total_sales:    int
    total_revenue:  float
    average_rating: float
    review_count:   int


# ── Output Schemas ─────────────────────────────────────────────────────


class VendorProfileOut(Schema):
    id:           UUID
    user_id:      str
    store_name:   str
    store_slug:   str
    tagline:      str
    description:  str
    logo_url:     str
    cover_url:    str
    city:         str
    state:        str
    country:      str
    instagram_url: str
    tiktok_url:   str
    twitter_url:  str
    website_url:  str
    is_verified:  bool
    is_active:    bool
    is_featured:  bool


class VendorDashboardOut(Schema):
    profile:         VendorProfileOut
    analytics:       AnalyticsOut
    setup_state:     SetupStateOut
    recent_activity: list[Any] = Field(default_factory=list)


# ── Input Schemas ──────────────────────────────────────────────────────


class VendorProfileUpdateIn(Schema):
    store_name:    str | None = None
    tagline:       str | None = None
    description:   str | None = None
    logo_url:      str | None = None
    cover_url:     str | None = None
    city:          str | None = None
    state:         str | None = None
    country:       str | None = None
    instagram_url: str | None = None
    tiktok_url:    str | None = None
    twitter_url:   str | None = None
    website_url:   str | None = None


class VendorPayoutIn(Schema):
    bank_name:                str
    bank_code:                str = ""
    account_name:             str
    account_number:           str
    paystack_recipient_code:  str = ""
