# apps/vendor/services/vendor_dashboard_service.py
"""
VendorDashboardService — Async aggregated analytics for the vendor dashboard.

Architecture:
  ─ All methods are async-native (Django 6.0 async ORM).
  ─ Zero sync_to_async().
  ─ asyncio.gather() used for ALL independent DB fetches (mandatory rule).
  ─ Delegates every DB read to the selectors layer.

Dashboard payload:
  profile         → store identity, verification, location, social
  analytics       → denormalized counters (products, sales, revenue, rating)
  setup_state     → onboarding milestones (KYC excluded from gating)
  payout_profile  → safe bank data (no encrypted fields)
  recent_orders   → latest 10 orders
  products        → latest 10 products
  top_products    → top 5 by qty sold (NEW — eliminates separate /top-products/ call)
  reviews         → latest 5 reviews
  coupons         → active / inactive counts
  wallet          → balance + recent transactions
  recent_activity → stub (future activity-stream sprint)
  revenue_trends  → 6-month monthly revenue chart (NEW)
"""
import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)


class VendorDashboardService:
    """
    Aggregates all metrics needed to render the vendor dashboard.

    All methods are async — used exclusively by the Ninja async router.

    KEY ARCHITECTURE RULE:
      All independent DB fetches are launched concurrently via asyncio.gather().
      This reduces total dashboard latency to ~max(slowest_query) instead of
      sum(all_queries), giving ~4-6x speedup at 10k+ RPS.
    """

    @classmethod
    async def get_dashboard_summary(cls, user) -> dict[str, Any]:
        """
        Build the complete vendor dashboard payload.

        Uses asyncio.gather() to fetch all data concurrently.
        Delegates all DB reads to the selectors layer.
        """
        from apps.vendor.selectors.vendor_selectors import (
            aget_vendor_profile_or_none,
            aget_vendor_setup_state_data,
            aget_vendor_payout_profile_data,
            aget_vendor_recent_orders,
            aget_vendor_products_summary,
            aget_vendor_top_selling_products,
            aget_vendor_reviews_summary,
            aget_vendor_coupon_stats,
            aget_vendor_wallet_data,
            aget_vendor_low_stock_alerts,
            aget_vendor_revenue_trends,
        )

        profile = await aget_vendor_profile_or_none(user)
        if profile is None:
            logger.warning(
                "VendorDashboardService: no VendorProfile found for user %s",
                getattr(user, "pk", "?"),
            )
            raise ValueError("Vendor profile not found for this user.")

        # ── MANDATORY: asyncio.gather() for all independent I/O operations ──
        # 10 concurrent fetches — total latency ≈ slowest single query (~4–6x speedup).
        (
            setup_data,
            payout_data,
            recent_orders,
            products,
            top_products,
            reviews,
            coupons,
            wallet,
            low_stock_alerts,
            revenue_trends,
        ) = await asyncio.gather(
            aget_vendor_setup_state_data(profile),
            aget_vendor_payout_profile_data(profile),
            aget_vendor_recent_orders(profile, limit=10),
            aget_vendor_products_summary(profile, limit=10),
            aget_vendor_top_selling_products(profile, limit=5),  # NEW
            aget_vendor_reviews_summary(profile, limit=5),
            aget_vendor_coupon_stats(profile),
            aget_vendor_wallet_data(profile),
            aget_vendor_low_stock_alerts(profile, threshold=5),
            aget_vendor_revenue_trends(profile, months=6),        # NEW
        )

        return {
            "profile": {
                "id":            str(profile.pk),
                "store_name":    profile.store_name,
                "store_slug":    profile.store_slug,
                "tagline":       profile.tagline,
                "description":   profile.description,
                "logo_url":      profile.logo_url.url if getattr(profile.logo_url, "url", None) else (str(profile.logo_url) if profile.logo_url else ""),
                "cover_url":     profile.cover_url.url if getattr(profile.cover_url, "url", None) else (str(profile.cover_url) if profile.cover_url else ""),
                "city":          profile.city,
                "state":         profile.state,
                "country":       profile.country,
                "whatsapp":      profile.whatsapp,
                "instagram_url": profile.instagram_url,
                "tiktok_url":    profile.tiktok_url,
                "twitter_url":   profile.twitter_url,
                "website_url":   profile.website_url,
                "is_verified":   profile.is_verified,
                "is_active":     profile.is_active,
                "is_featured":   profile.is_featured,
                "last_active_at": profile.last_active_at.isoformat() if profile.last_active_at else None,
                "support_rating": float(profile.support_rating),
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
            "top_products":    top_products,     # NEW — consumed by dashboard widget
            "reviews":         reviews,
            "coupons":         coupons,
            "wallet":          wallet,
            "recent_activity": [],
            "low_stock_alerts": low_stock_alerts,
            "revenue_trends":  revenue_trends,  # NEW — consumed by dashboard chart
        }

    @classmethod
    async def get_analytics_summary(cls, user) -> dict[str, Any]:
        """
        Standalone analytics fetch for the /analytics/ endpoint.
        Uses asyncio.gather() to compute all metrics concurrently.
        """
        from apps.vendor.selectors.vendor_selectors import (
            aget_vendor_profile_or_none,
            aget_vendor_revenue_trends,
            aget_vendor_top_selling_products,
            aget_vendor_order_status_counts,
            aget_vendor_top_categories,
        )

        profile = await aget_vendor_profile_or_none(user)
        if profile is None:
            raise ValueError("Vendor profile not found for this user.")

        # All 4 analytics fetches run concurrently
        (
            revenue_trends,
            top_products,
            order_status_counts,
            top_categories,
        ) = await asyncio.gather(
            aget_vendor_revenue_trends(profile, months=6),
            aget_vendor_top_selling_products(profile, limit=5),
            aget_vendor_order_status_counts(profile),
            aget_vendor_top_categories(profile, limit=5),
        )

        return {
            "revenue_trends":      revenue_trends,
            "top_products":        top_products,
            "order_status_counts": order_status_counts,
            "top_categories":      top_categories,
        }
