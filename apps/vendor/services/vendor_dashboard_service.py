# apps/vendor/services/vendor_dashboard_service.py
"""
VendorDashboardService — Async aggregated analytics for the vendor dashboard.

All methods are async-native (Django 6.0 async ORM).
Zero sync_to_async(). Delegates reads to selectors layer.

Dashboard payload summary:
  profile       → store identity, verification, location, social
  setup_state   → onboarding milestones (KYC excluded from gating)
  analytics     → products, sales, revenue, ratings (denormalized counters)
  orders        → recent 10 orders
  products      → recent 10 products
  reviews       → recent 5 reviews
  coupons       → active/inactive counts
  wallet        → balance + recent transactions
  recent_activity → stub (future activity-stream sprint)
"""
import logging
from typing import Any

logger = logging.getLogger(__name__)


class VendorDashboardService:
    """
    Aggregates all metrics needed to render the vendor dashboard.
    All methods are async — used exclusively by the Ninja async router.
    """

    @classmethod
    async def get_dashboard_summary(cls, user) -> dict[str, Any]:
        """
        Build the complete vendor dashboard payload.
        Delegates all DB reads to the selectors layer to keep this service clean.
        """
        from apps.vendor.selectors.vendor_selectors import (
            aget_vendor_profile_or_none,
            aget_vendor_setup_state_data,
            aget_vendor_payout_profile_data,
            aget_vendor_recent_orders,
            aget_vendor_products_summary,
            aget_vendor_reviews_summary,
            aget_vendor_coupon_stats,
            aget_vendor_wallet_data,
        )

        profile = await aget_vendor_profile_or_none(user)
        if profile is None:
            logger.warning(
                "VendorDashboardService: no VendorProfile found for user %s",
                getattr(user, "pk", "?"),
            )
            raise ValueError("Vendor profile not found for this user.")

        # ── Gather all data concurrently using Django's async ORM ──
        # (Sequential await is fine for now; can be replaced with asyncio.gather
        #  if benchmarks show latency gain worth the added complexity.)
        setup_data    = await aget_vendor_setup_state_data(profile)
        payout_data   = await aget_vendor_payout_profile_data(profile)
        recent_orders = await aget_vendor_recent_orders(profile, limit=10)
        products      = await aget_vendor_products_summary(profile, limit=10)
        reviews       = await aget_vendor_reviews_summary(profile, limit=5)
        coupons       = await aget_vendor_coupon_stats(profile)
        wallet        = await aget_vendor_wallet_data(profile)

        return {
            "profile": {
                "id":           str(profile.pk),
                "store_name":   profile.store_name,
                "store_slug":   profile.store_slug,
                "tagline":      profile.tagline,
                "description":  profile.description,
                "logo_url":     profile.logo_url,
                "cover_url":    profile.cover_url,
                "city":         profile.city,
                "state":        profile.state,
                "country":      profile.country,
                "whatsapp":     profile.whatsapp,
                "instagram_url": profile.instagram_url,
                "tiktok_url":   profile.tiktok_url,
                "twitter_url":  profile.twitter_url,
                "website_url":  profile.website_url,
                "is_verified":  profile.is_verified,
                "is_active":    profile.is_active,
                "is_featured":  profile.is_featured,
            },
            "analytics": {
                "total_products": profile.total_products,
                "total_sales":    profile.total_sales,
                "total_revenue":  float(profile.total_revenue),
                "average_rating": float(profile.average_rating),
                "review_count":   profile.review_count,
            },
            "setup_state":     setup_data,
            "payout_profile":  payout_data,
            "recent_orders":   recent_orders,
            "products":        products,
            "reviews":         reviews,
            "coupons":         coupons,
            "wallet":          wallet,
            "recent_activity": [],  # Future: activity-stream service sprint
        }
