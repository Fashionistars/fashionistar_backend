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
    subscription_tier:    str = "free"
    avg_fulfillment_days: float | None = None
    return_rate:          float = 0.0
    dispute_rate:         float = 0.0
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


# ── Migrated Analytics & List Output Schemas ──

class AnalyticsSummaryOut(Schema):
    todays_sales: str
    this_month_sales: str
    year_to_date_sales: str
    average_order_value: str
    total_customers: int
    review_count: int
    average_rating: str
    active_coupons: int
    inactive_coupons: int
    low_stock_count: int
    total_products: int
    total_sales: int
    total_revenue: str
    wallet_balance: str
    total_orders: int
    avg_order_value: float
    revenue_trend: float
    conversion_rate: float



class ChartPointOut(Schema):
    label: str
    value: float


class ChartResponseOut(Schema):
    status: str = "success"
    data: list[ChartPointOut]



class MonthlyOrderOut(Schema):
    month: int
    order_status: str
    count: int


class MonthlyProductOut(Schema):
    month: int
    count: int


class EarningTrackerOut(Schema):
    total_revenue: float
    pending_revenue: float = 0.0
    monthly_earnings: list[dict[str, Any]]


class CustomerBehaviorOut(Schema):
    hourly_distribution: list[dict[str, Any]]
    new_customers_this_month: int
    total_customers: int


class CategoryPerformanceOut(Schema):
    categories__name: str
    total_revenue: float
    order_count: int


class PaymentDistributionOut(Schema):
    payment_status: str
    count: int
    percentage: float


class ProductListItemOut(Schema):
    id: str
    pid: str
    title: str
    price: float
    stock_qty: int
    status: str
    category__name: str | None = None
    date: datetime


class VendorOrderItemOut(Schema):
    id: UUID
    product_title: str
    product_pid: str
    qty: int
    price: float
    subtotal: float
    product_title_snapshot: str | None = None
    product_sku_snapshot: str | None = None
    variant_description_snapshot: str | None = None
    quantity: int | None = None
    unit_price: float | None = None
    line_total: float | None = None
    measurement_data: dict[str, Any] | None = None


class OrderListItemOut(Schema):
    id: UUID
    oid: str
    buyer_email: str
    buyer_full_name: str
    order_status: str
    payment_status: str
    total_price: float
    date: datetime
    total: float | None = None


class OrderDetailOut(Schema):
    id: UUID
    oid: str
    buyer_email: str
    buyer_full_name: str
    order_status: str
    payment_status: str
    total_price: float
    date: datetime
    total: float | None = None
    items: list[VendorOrderItemOut] = []


class ReviewListItemOut(Schema):
    review_product__id: str
    review_product__rating: int
    review_product__review: str
    review_product__date: datetime
    title: str


class CouponListItemOut(Schema):
    id: str
    code: str
    discount: int
    discount_type: str | None = None
    valid_until: datetime | None = None
    active: bool


class OrderListResponseOut(Schema):
    status: str = "success"
    count: int
    data: list[OrderListItemOut]


class ReviewListResponseOut(Schema):
    status: str = "success"
    count: int
    data: list[ReviewListItemOut]


class CouponListResponseOut(Schema):
    status: str = "success"
    count: int
    data: list[CouponListItemOut]


