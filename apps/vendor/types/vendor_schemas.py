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

from datetime import datetime
from typing import Any
from uuid import UUID
from decimal import Decimal

from ninja import Schema
from pydantic import Field


# ══════════════════════════════════════════════════════════════════
#  Sub-schemas
# ══════════════════════════════════════════════════════════════════


class SetupStateOut(Schema):
    current_step:          int  = 1
    profile_complete:      bool = False
    bank_details:          bool = False
    id_verified:           bool = False   # informational: KYC future sprint, does NOT gate access
    first_product:         bool = False
    onboarding_done:       bool = False
    completion_percentage: int  = 0       # Computed in selector, not a DB column


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


class TopProductOut(Schema):
    """
    Top-selling product entry — returned in both dashboard payload and
    the standalone /top-products/ endpoint.

    Fields:
        id:        Product UUID (str).
        title:     Product title.
        price:     Unit price (float, NGN).
        stock_qty: Current stock quantity.
        total_qty: Total units sold across all orders (None if no orders yet).
    """
    id:        str
    title:     str
    price:     float = 0.0
    stock_qty: int   = 0
    total_qty: int | None = None


class RevenueDataPointOut(Schema):
    """
    Monthly revenue aggregation for a single calendar month.

    Fields:
        month:         Calendar month number (1 = Jan … 12 = Dec).
        total_revenue: Total gross revenue for this month (float, NGN).
    """
    month:         int   = 1
    total_revenue: float = 0.0


# ══════════════════════════════════════════════════════════════════
#  Output Schemas
# ══════════════════════════════════════════════════════════════════


class VendorProfileOut(Schema):
    id:            UUID
    user_id:       str
    user_email:    str
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
    total_products: int = 0
    total_sales:    int = 0
    total_revenue:  float = 0.0
    average_rating: float = 0.0
    review_count:   int = 0
    wallet_balance: float = 0.0
    is_verified:   bool
    is_active:     bool
    is_featured:   bool
    last_active_at: datetime | None = None
    support_rating: float = 5.00
    setup_state:   SetupStateOut | None = None


class VendorDashboardOut(Schema):
    """
    Full vendor dashboard payload — single endpoint response.

    All independent data sections are fetched concurrently via asyncio.gather()
    in VendorDashboardService.get_dashboard_summary() and returned here.

    Added in this revision:
        top_products:   list[TopProductOut]        — top N by qty sold
        revenue_trends: list[RevenueDataPointOut]  — 6-month revenue chart
    """
    profile:             dict[str, Any]
    analytics:           AnalyticsOut
    setup_state:         SetupStateOut
    payout_profile:      PayoutProfileOut          = Field(default_factory=PayoutProfileOut)
    recent_orders:       list[Any]                 = Field(default_factory=list)
    products:            list[Any]                 = Field(default_factory=list)
    top_products:        list[TopProductOut]        = Field(default_factory=list)
    reviews:             list[Any]                 = Field(default_factory=list)
    coupons:             CouponStatsOut             = Field(default_factory=CouponStatsOut)
    wallet:              WalletOut                  = Field(default_factory=WalletOut)
    recent_activity:     list[Any]                 = Field(default_factory=list)
    low_stock_alerts:    list[Any]                 = Field(default_factory=list)
    revenue_trends:      list[RevenueDataPointOut]  = Field(default_factory=list)


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
