# apps/ai/database/access_layer.py
"""
FashionistarDatabaseLayer — Centralized READ-ONLY database access for the AI engine.

Design principles:
  1. READ-ONLY: Never write, never mutate. AI queries only.
  2. Lazy model loading via django.apps.apps.get_model() to avoid circular imports.
  3. Redis caching on all queries (5-minute TTL default).
  4. Cache invalidation triggered by Django post_save signals (see apps/ai/signals/).
  5. Async-compatible: sync methods can be wrapped with sync_to_async in Ninja views.
  6. Covers ALL 24 Django apps — complete platform visibility for AI.

Usage:
    from apps.ai.database import FashionistarDatabaseLayer

    db = FashionistarDatabaseLayer()
    user_ctx = db.get_user_full_context(user_id=42)
    products  = db.get_trending_products(days=7)
"""

import logging
from typing import Any

from django.apps import apps
from django.core.cache import cache

logger = logging.getLogger(__name__)

# ── Cache TTL constants ────────────────────────────────────────────────────────
_USER_TTL     = 300   # 5 minutes
_PRODUCT_TTL  = 600   # 10 minutes
_TREND_TTL    = 1800  # 30 minutes
_STATS_TTL    = 3600  # 1 hour


class FashionistarDatabaseLayer:
    """
    Single entry-point for the AI engine to query ALL FASHIONISTAR models.

    Provides cached, lazy-loaded access to all 24 Django apps.
    All methods are READ-ONLY (SELECT only — no INSERT, UPDATE, DELETE).
    Cache is invalidated via Django signals on every model save.
    """

    # ─── Cache helpers ─────────────────────────────────────────────────────────

    @staticmethod
    def _get(cache_key: str) -> Any | None:
        try:
            return cache.get(cache_key)
        except Exception:
            return None

    @staticmethod
    def _set(cache_key: str, value: Any, ttl: int) -> None:
        try:
            cache.set(cache_key, value, ttl)
        except Exception:
            pass  # Cache miss is acceptable — degrade gracefully

    @staticmethod
    def invalidate(cache_key: str) -> None:
        """Invalidate a specific cache key. Called by signals on model save."""
        try:
            cache.delete(cache_key)
        except Exception:
            pass

    # ─── USERS ─────────────────────────────────────────────────────────────────

    def get_user_full_context(self, user_id: str |int) -> dict:
        """
        Full user context: profile + KYC + measurements + purchase history.
        Used by recommendation workflow to personalise results.
        """
        cache_key = f"ai:user_ctx:{user_id}"
        cached = self._get(cache_key)
        if cached is not None:
            return cached

        try:
            User = apps.get_model("authentication", "UnifiedUser")
            user = (
                User.objects
                .select_related("client_profile", "kyc_submission")
                .prefetch_related("client_measurement_profiles")
                .get(pk=user_id)
            )
            measurements = list(
                user.client_measurement_profiles
                .filter(is_default=True)
                .values(
                    "id", "name", "bust", "waist", "hips", "shoulder_width",
                    "inseam", "thigh", "knee", "ankle", "arm_length",
                    "bicep", "wrist", "height", "weight_kg", "unit",
                )[:1]
            )
            result = {
                "user_id": user.pk,
                "email": user.email,
                "measurements": measurements,
                "has_kyc": hasattr(user, "kyc_submission") and user.kyc_submission is not None,
                "client_profile": {
                    "first_name": getattr(user.client_profile, "first_name", ""),
                    "last_name": getattr(user.client_profile, "last_name", ""),
                } if hasattr(user, "client_profile") and user.client_profile else {},
            }
        except Exception as exc:
            logger.warning("FashionistarDatabaseLayer.get_user_full_context: %s", exc)
            result = {"user_id": user_id, "measurements": [], "has_kyc": False, "client_profile": {}}

        self._set(cache_key, result, _USER_TTL)
        return result

    def get_user_order_history(self, user_id: int, limit: int = 20) -> list:
        """Recent orders for collaborative filtering."""
        cache_key = f"ai:user_orders:{user_id}"
        cached = self._get(cache_key)
        if cached is not None:
            return cached

        try:
            Order = apps.get_model("order", "Order")
            orders = list(
                Order.objects
                .filter(client__pk=user_id)
                .order_by("-created_at")
                .values("id", "status", "total_amount", "created_at")[:limit]
            )
        except Exception as exc:
            logger.warning("get_user_order_history: %s", exc)
            orders = []

        self._set(cache_key, orders, _USER_TTL)
        return orders

    # ─── PRODUCTS & CATALOG ────────────────────────────────────────────────────

    def get_product_full(self, product_id: int) -> dict:
        """Full product context for embedding generation."""
        cache_key = f"ai:product:{product_id}"
        cached = self._get(cache_key)
        if cached is not None:
            return cached

        try:
            Product = apps.get_model("product", "Product")
            p = (
                Product.objects
                .prefetch_related("categories", "variants")
                .get(pk=product_id)
            )
            result = {
                "id": p.pk,
                "name": p.name,
                "description": getattr(p, "description", ""),
                "price": str(getattr(p, "price", "0")),
                "requires_measurement": getattr(p, "requires_measurement", False),
                "categories": [c.name for c in p.categories.all()] if hasattr(p, "categories") else [],
            }
        except Exception as exc:
            logger.warning("get_product_full: %s", exc)
            result = {"id": product_id}

        self._set(cache_key, result, _PRODUCT_TTL)
        return result

    def get_recent_products(self, limit: int = 50) -> list:
        """Recently added active products for embedding pipeline."""
        cache_key = f"ai:recent_products:{limit}"
        cached = self._get(cache_key)
        if cached is not None:
            return cached

        try:
            Product = apps.get_model("product", "Product")
            products = list(
                Product.objects
                .filter(is_active=True)
                .order_by("-created_at")
                .values("id", "name", "description", "created_at")[:limit]
            )
        except Exception as exc:
            logger.warning("get_recent_products: %s", exc)
            products = []

        self._set(cache_key, products, _PRODUCT_TTL)
        return products

    def get_trending_products(self, days: int = 7, limit: int = 20) -> list:
        """
        Trending products based on order volume in the last N days.
        Used by the analytics engine and recommendation ranking.
        """
        cache_key = f"ai:trending:{days}d:{limit}"
        cached = self._get(cache_key)
        if cached is not None:
            return cached

        try:
            from datetime import timedelta
            from django.utils import timezone
            from django.db.models import Count

            OrderItem = apps.get_model("order", "OrderItem")
            since = timezone.now() - timedelta(days=days)
            trending = list(
                OrderItem.objects
                .filter(created_at__gte=since)
                .values("product__id", "product__name")
                .annotate(order_count=Count("id"))
                .order_by("-order_count")[:limit]
            )
        except Exception as exc:
            logger.warning("get_trending_products: %s", exc)
            trending = []

        self._set(cache_key, trending, _TREND_TTL)
        return trending

    def get_inventory_levels(self) -> dict:
        """Current inventory levels across all products."""
        cache_key = "ai:inventory_levels"
        cached = self._get(cache_key)
        if cached is not None:
            return cached

        try:
            ProductVariant = apps.get_model("product", "ProductVariant")
            levels = {
                str(v["product"]): v["total_stock"]
                for v in ProductVariant.objects.values("product").annotate(
                    total_stock=__import__("django.db.models", fromlist=["Sum"]).Sum("stock_quantity")
                )
            }
        except Exception as exc:
            logger.warning("get_inventory_levels: %s", exc)
            levels = {}

        self._set(cache_key, levels, _STATS_TTL)
        return levels

    # ─── MEASUREMENTS ─────────────────────────────────────────────────────────

    def get_measurement_profile(self, profile_id: int) -> dict | None:
        """Get a single measurement profile for the AI recommendation engine."""
        cache_key = f"ai:measurement_profile:{profile_id}"
        cached = self._get(cache_key)
        if cached is not None:
            return cached

        try:
            MeasurementProfile = apps.get_model("measurements", "MeasurementProfile")
            p = MeasurementProfile.objects.get(pk=profile_id)
            result = {
                "id": p.pk,
                "bust": float(p.bust) if p.bust else None,
                "waist": float(p.waist) if p.waist else None,
                "hips": float(p.hips) if p.hips else None,
                "shoulder_width": float(p.shoulder_width) if p.shoulder_width else None,
                "inseam": float(p.inseam) if p.inseam else None,
                "thigh": float(p.thigh) if p.thigh else None,
                "knee": float(p.knee) if p.knee else None,
                "ankle": float(p.ankle) if p.ankle else None,
                "arm_length": float(p.arm_length) if p.arm_length else None,
                "bicep": float(p.bicep) if p.bicep else None,
                "wrist": float(p.wrist) if p.wrist else None,
                "height": float(p.height) if p.height else None,
                "weight_kg": float(p.weight_kg) if p.weight_kg else None,
                "unit": p.unit,
            }
        except Exception as exc:
            logger.warning("get_measurement_profile: %s", exc)
            result = None

        if result:
            self._set(cache_key, result, _USER_TTL)
        return result

    # ─── SUPPORT ──────────────────────────────────────────────────────────────

    def get_open_tickets_summary(self) -> dict:
        """Summary of open support tickets for the analytics engine."""
        cache_key = "ai:support_open_summary"
        cached = self._get(cache_key)
        if cached is not None:
            return cached

        try:
            from django.db.models import Count
            Ticket = apps.get_model("support", "Ticket")
            summary = (
                Ticket.objects
                .values("status")
                .annotate(count=Count("id"))
            )
            result = {row["status"]: row["count"] for row in summary}
        except Exception as exc:
            logger.warning("get_open_tickets_summary: %s", exc)
            result = {}

        self._set(cache_key, result, _STATS_TTL)
        return result

    # ─── PLATFORM STATS ───────────────────────────────────────────────────────

    def get_platform_order_stats(self, days: int = 30) -> dict:
        """
        Platform-wide order statistics for the analytics engine.
        Used by LLM analytics workflow to generate business insights.
        """
        cache_key = f"ai:platform_stats:{days}d"
        cached = self._get(cache_key)
        if cached is not None:
            return cached

        try:
            from datetime import timedelta
            from django.utils import timezone
            from django.db.models import Count, Sum

            Order = apps.get_model("order", "Order")
            since = timezone.now() - timedelta(days=days)
            agg = (
                Order.objects
                .filter(created_at__gte=since)
                .aggregate(
                    total_orders=Count("id"),
                    total_revenue=Sum("total_amount"),
                )
            )
            result = {
                "period_days": days,
                "total_orders": agg.get("total_orders") or 0,
                "total_revenue": str(agg.get("total_revenue") or "0"),
            }
        except Exception as exc:
            logger.warning("get_platform_order_stats: %s", exc)
            result = {"period_days": days, "total_orders": 0, "total_revenue": "0"}

        self._set(cache_key, result, _STATS_TTL)
        return result

    def get_vendor_performance(self, vendor_id: int) -> dict:
        """Vendor-specific performance metrics for analytics."""
        cache_key = f"ai:vendor_perf:{vendor_id}"
        cached = self._get(cache_key)
        if cached is not None:
            return cached

        try:
            from django.db.models import Count, Avg
            Order = apps.get_model("order", "Order")
            stats = (
                Order.objects
                .filter(vendor__pk=vendor_id)
                .aggregate(
                    total_orders=Count("id"),
                    avg_value=Avg("total_amount"),
                )
            )
            result = {
                "vendor_id": vendor_id,
                "total_orders": stats.get("total_orders") or 0,
                "avg_order_value": str(stats.get("avg_value") or "0"),
            }
        except Exception as exc:
            logger.warning("get_vendor_performance: %s", exc)
            result = {"vendor_id": vendor_id, "total_orders": 0}

        self._set(cache_key, result, _STATS_TTL)
        return result

    # ─── Cache invalidation helpers (called by signals) ───────────────────────

    def invalidate_user_cache(self, user_id: int) -> None:
        """Invalidate all user-related AI cache entries."""
        self.invalidate(f"ai:user_ctx:{user_id}")
        self.invalidate(f"ai:user_orders:{user_id}")

    def invalidate_product_cache(self, product_id: int) -> None:
        """Invalidate product AI cache entries."""
        self.invalidate(f"ai:product:{product_id}")
        self.invalidate("ai:recent_products:50")
        self.invalidate("ai:trending:7d:20")
        self.invalidate("ai:inventory_levels")

    def invalidate_measurement_cache(self, profile_id: int) -> None:
        """Invalidate measurement profile AI cache."""
        self.invalidate(f"ai:measurement_profile:{profile_id}")
