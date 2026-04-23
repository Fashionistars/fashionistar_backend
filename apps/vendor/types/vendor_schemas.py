# apps/vendor/types/vendor_schemas.py
"""
Pydantic / Django-Ninja schemas for the async Vendor API.

Contract rules:
  ─ Out schemas: strict types, no Optional for required response fields.
  ─ In schemas: use None defaults for optional partial-update fields.
  ─ All monetary values returned as float (safe for JSON serialisation).
  ─ UUIDs returned as UUID type (Ninja serialises to string automatically).
"""
from __future__ import annotations

from typing import Any
from uuid import UUID
from decimal import Decimal

from ninja import Schema
from pydantic import Field


# ══════════════════════════════════════════════════════════════════
#  Sub-schemas
# ══════════════════════════════════════════════════════════════════


class SetupStateOut(Schema):
    current_step:          int
    profile_complete:      bool
    bank_details:          bool
    id_verified:           bool   # informational: KYC future sprint, does NOT gate access
    first_product:         bool
    onboarding_done:       bool
    completion_percentage: int


class AnalyticsOut(Schema):
    total_products: int
    total_sales:    int
    total_revenue:  float
    average_rating: float
    review_count:   int


class PayoutProfileOut(Schema):
    bank_name:                str = ""
    bank_code:                str = ""
    account_name:             str = ""
    account_last4:            str = ""
    paystack_recipient_code:  str = ""
    is_verified:              bool = False


class WalletOut(Schema):
    balance:              float = 0.0
    recent_transactions:  list[Any] = Field(default_factory=list)


class CouponStatsOut(Schema):
    active:   int = 0
    inactive: int = 0


# ══════════════════════════════════════════════════════════════════
#  Output Schemas
# ══════════════════════════════════════════════════════════════════


class VendorProfileOut(Schema):
    id:            UUID
    user_id:       str
    store_name:    str
    store_slug:    str
    tagline:       str
    description:   str
    logo_url:      str
    cover_url:     str
    city:          str
    state:         str
    country:       str
    whatsapp:      str = ""
    instagram_url: str = ""
    tiktok_url:    str = ""
    twitter_url:   str = ""
    website_url:   str = ""
    is_verified:   bool
    is_active:     bool
    is_featured:   bool


class VendorDashboardOut(Schema):
    profile:          dict[str, Any]
    analytics:        AnalyticsOut
    setup_state:      SetupStateOut
    payout_profile:   PayoutProfileOut   = Field(default_factory=PayoutProfileOut)
    recent_orders:    list[Any]          = Field(default_factory=list)
    products:         list[Any]          = Field(default_factory=list)
    reviews:          list[Any]          = Field(default_factory=list)
    coupons:          CouponStatsOut     = Field(default_factory=CouponStatsOut)
    wallet:           WalletOut          = Field(default_factory=WalletOut)
    recent_activity:  list[Any]          = Field(default_factory=list)


# ══════════════════════════════════════════════════════════════════
#  Input Schemas
# ══════════════════════════════════════════════════════════════════


class VendorProfileUpdateIn(Schema):
    """Partial update of store profile fields. All fields optional."""
    store_name:     str | None = None
    tagline:        str | None = None
    description:    str | None = None
    logo_url:       str | None = None
    cover_url:      str | None = None
    city:           str | None = None
    state:          str | None = None
    country:        str | None = None
    whatsapp:       str | None = None
    instagram_url:  str | None = None
    tiktok_url:     str | None = None
    twitter_url:    str | None = None
    website_url:    str | None = None
    collection_ids: list[str] | None = None  # List of Collections PKs


class VendorPayoutIn(Schema):
    bank_name:               str
    bank_code:               str = ""
    account_name:            str
    account_number:          str
    paystack_recipient_code: str = ""


class VendorPinIn(Schema):
    pin: str = Field(..., min_length=4, max_length=4, pattern=r"^\d{4}$")


class VendorPinVerifyIn(Schema):
    pin: str = Field(..., min_length=4, max_length=4, pattern=r"^\d{4}$")
