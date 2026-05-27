# apps/vendor/admin_backend/schemas.py
"""Django Ninja typed schemas for the vendor admin API."""

from __future__ import annotations
from datetime import datetime
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel


class AdminVendorListSchema(BaseModel):
    id: str
    store_name: str
    store_slug: str
    tagline: Optional[str] = None
    country: Optional[str] = None
    city: Optional[str] = None
    is_verified: bool
    is_active: bool
    is_featured: bool
    is_deleted: bool
    total_products: int
    total_sales: int
    total_revenue: Decimal
    average_rating: Decimal
    review_count: int
    wallet_balance: Decimal
    product_count: int = 0
    user_email: Optional[str] = None
    user_phone: Optional[str] = None
    user_member_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class AdminVendorDetailSchema(AdminVendorListSchema):
    description: Optional[str] = None
    state: Optional[str] = None
    address: Optional[str] = None
    instagram_url: Optional[str] = None
    tiktok_url: Optional[str] = None
    twitter_url: Optional[str] = None
    website_url: Optional[str] = None
    whatsapp: Optional[str] = None
    opening_time: Optional[str] = None
    closing_time: Optional[str] = None
    business_hours: Optional[dict] = None
    cash_payment_mode: Optional[str] = None
    setup_complete: bool = False
    payout_verified: bool = False
    deleted_at: Optional[datetime] = None


class AdminVendorStatsSchema(BaseModel):
    total: int
    approved: int
    pending: int
    suspended: int
    featured: int


class AdminVendorSuspendSchema(BaseModel):
    reason: str


class AdminVendorCommissionSchema(BaseModel):
    commission_rate: Decimal


class AdminVendorActionResponse(BaseModel):
    success: bool = True
    message: str
    vendor_id: Optional[str] = None
