# apps/vendor/admin_backend/api.py
"""
Django Ninja async read API for the vendor admin domain.

GET  /api/admin/vendor/                    → paginated vendor list
GET  /api/admin/vendor/stats/              → KPI stats
GET  /api/admin/vendor/{id}/               → vendor detail
GET  /api/admin/vendor/{id}/products/      → vendor products list
"""

from __future__ import annotations
import logging
from typing import Optional
from ninja import Router
from apps.admin_backend.permissions import admin_auth
from .selectors import (
    list_vendors_admin,
    get_vendor_detail_admin,
    get_vendor_products_admin,
    get_vendor_stats_admin,
)
from .schemas import AdminVendorStatsSchema

logger = logging.getLogger(__name__)
router = Router(tags=["Admin - Vendor"])


@router.get("/", summary="Admin: List Vendors", auth=admin_auth)
async def admin_list_vendors(
    request,
    is_verified: Optional[bool] = None,
    is_active: Optional[bool] = None,
    is_featured: Optional[bool] = None,
    country: Optional[str] = None,
    search: Optional[str] = None,
    ordering: str = "-created_at",
    page: int = 1,
    page_size: int = 25,
):
    payload = await list_vendors_admin(
        is_verified=is_verified, is_active=is_active, is_featured=is_featured,
        country=country, search=search, ordering=ordering,
        page=page, page_size=page_size,
    )

    def serialize_vendor(vendor):
        return {
            "id": str(vendor.pk),
            "store_name": vendor.store_name,
            "store_slug": vendor.store_slug,
            "tagline": vendor.tagline,
            "country": vendor.country,
            "city": vendor.city,
            "is_verified": vendor.is_verified,
            "is_active": vendor.is_active,
            "is_featured": vendor.is_featured,
            "is_deleted": vendor.is_deleted,
            "total_products": vendor.total_products,
            "total_sales": vendor.total_sales,
            "total_revenue": float(vendor.total_revenue),
            "average_rating": float(vendor.average_rating),
            "review_count": vendor.review_count,
            "wallet_balance": float(vendor.wallet_balance),
            "last_active_at": vendor.last_active_at.isoformat() if vendor.last_active_at else None,
            "support_rating": float(vendor.support_rating),
            "product_count": getattr(vendor, "product_count", 0),
            "user_email": vendor.user.email if vendor.user else None,
            "user_phone": str(vendor.user.phone) if (vendor.user and vendor.user.phone) else None,
            "user_member_id": vendor.user.member_id if vendor.user else None,
            "created_at": vendor.created_at.isoformat() if vendor.created_at else None,
            "updated_at": vendor.updated_at.isoformat() if vendor.updated_at else None,
        }

    payload["results"] = [serialize_vendor(v) for v in payload.get("results", [])]
    return payload


@router.get("/stats/", response=AdminVendorStatsSchema, summary="Admin: Vendor KPI Stats", auth=admin_auth)
async def admin_vendor_stats(request):
    return await get_vendor_stats_admin()


@router.get("/{vendor_id}/", summary="Admin: Vendor Detail", auth=admin_auth)
async def admin_vendor_detail(request, vendor_id: str):
    from apps.vendor.models import VendorProfile
    try:
        vendor = await get_vendor_detail_admin(vendor_id=vendor_id)
    except VendorProfile.DoesNotExist:
        return {"success": False, "message": "Vendor not found."}

    setup = getattr(vendor, "vendor_setup_state", None)
    payout = getattr(vendor, "vendor_payout_profile", None)

    return {
        "id": str(vendor.pk),
        "store_name": vendor.store_name,
        "store_slug": vendor.store_slug,
        "tagline": vendor.tagline,
        "description": vendor.description,
        "country": vendor.country,
        "city": vendor.city,
        "state": vendor.state,
        "address": vendor.address,
        "is_verified": vendor.is_verified,
        "is_active": vendor.is_active,
        "is_featured": vendor.is_featured,
        "is_deleted": vendor.is_deleted,
        "total_products": vendor.total_products,
        "total_sales": vendor.total_sales,
        "total_revenue": float(vendor.total_revenue),
        "average_rating": float(vendor.average_rating),
        "review_count": vendor.review_count,
        "wallet_balance": float(vendor.wallet_balance),
        "last_active_at": vendor.last_active_at.isoformat() if vendor.last_active_at else None,
        "support_rating": float(vendor.support_rating),
        "cash_payment_mode": vendor.cash_payment_mode,
        "instagram_url": vendor.instagram_url,
        "tiktok_url": vendor.tiktok_url,
        "twitter_url": vendor.twitter_url,
        "website_url": vendor.website_url,
        "whatsapp": vendor.whatsapp,
        "user_email": vendor.user.email if vendor.user else None,
        "user_member_id": vendor.user.member_id if vendor.user else None,
        "setup_complete": getattr(setup, "onboarding_done", False),
        "payout_verified": getattr(payout, "is_verified", False),
        "created_at": vendor.created_at.isoformat(),
        "updated_at": vendor.updated_at.isoformat(),
        "deleted_at": vendor.deleted_at.isoformat() if vendor.deleted_at else None,
    }


@router.get("/{vendor_id}/products/", summary="Admin: Vendor Products", auth=admin_auth)
async def admin_vendor_products(
    request, vendor_id: str, page: int = 1, page_size: int = 25
):
    payload = await get_vendor_products_admin(
        vendor_id=vendor_id, page=page, page_size=page_size
    )

    def serialize_product(product):
        return {
            "id": str(product.pk),
            "title": product.title,
            "slug": product.slug,
            "sku": product.sku,
            "price": float(product.price),
            "stock_qty": product.stock_qty,
            "is_active": product.is_active,
            "created_at": product.created_at.isoformat() if product.created_at else None,
            "updated_at": product.updated_at.isoformat() if product.updated_at else None,
        }

    payload["results"] = [serialize_product(p) for p in payload.get("results", [])]
    return payload
