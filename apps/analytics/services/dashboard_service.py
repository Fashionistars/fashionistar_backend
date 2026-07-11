"""
apps/analytics/services/dashboard_service.py
=============================================
Internal observability dashboard service for analytics system health.

Provides pre-computed metrics for admin-only dashboard endpoints:
  - Ingestion rate graph
  - Query latency distribution
  - Storage growth by table
  - Error rate by endpoint
  - Cache hit/miss rates

All data is cached for 60 seconds for fast admin panel rendering.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from django.core.cache import cache
from django.db import connection
from django.db.models import Avg, Count, Q
from django.utils import timezone

from apps.analytics.models import (
    Alert,
    BusinessMetric,
    Metric,
    PerformanceMetric,
    UserActivity,
)

logger = logging.getLogger(__name__)


class DashboardService:
    """
    Pre-computed analytics system health dashboard data.

    All methods return dicts suitable for JSON API responses.
    Results are cached for 60 seconds.
    """

    CACHE_PREFIX = "analytics:dashboard:"
    CACHE_TIMEOUT = 60  # 60 seconds

    # ========================================================================
    # Main Dashboard
    # ========================================================================

    @classmethod
    async def aget_system_overview(cls) -> dict[str, Any]:
        """
        Get a comprehensive system overview for the analytics dashboard.

        Returns:
            dict: Aggregated system health metrics.
        """
        cache_key = f"{cls.CACHE_PREFIX}system_overview"
        cached = cache.get(cache_key)
        if cached:
            return cached

        now = timezone.now()
        last_24h = now - timedelta(hours=24)
        last_1h = now - timedelta(hours=1)

        # Table row counts (storage growth)
        table_counts = await cls._aget_table_counts()

        # Ingestion rates
        ingestion_24h = await Metric.objects.filter(timestamp__gte=last_24h).acount()
        ingestion_1h = await Metric.objects.filter(timestamp__gte=last_1h).acount()

        # Performance metrics
        perf_24h = await PerformanceMetric.objects.filter(timestamp__gte=last_24h).acount()
        perf_errors = await PerformanceMetric.objects.filter(
            timestamp__gte=last_24h,
            status_code__gte=400,
        ).acount()

        # Active alerts
        firing_alerts = await Alert.objects.filter(status="firing").acount()

        # User activity
        activity_24h = await UserActivity.objects.filter(timestamp__gte=last_24h).acount()

        # Business metrics count
        business_count = await BusinessMetric.objects.acount()

        overview = {
            "generated_at": now.isoformat(),
            "ingestion": {
                "metrics_24h": ingestion_24h,
                "metrics_1h": ingestion_1h,
                "rate_per_minute": round(ingestion_1h / 60, 2) if ingestion_1h else 0,
            },
            "performance": {
                "records_24h": perf_24h,
                "errors_24h": perf_errors,
                "error_rate": round((perf_errors / perf_24h * 100), 2) if perf_24h else 0,
            },
            "alerts": {
                "firing": firing_alerts,
            },
            "activity": {
                "events_24h": activity_24h,
            },
            "business": {
                "total_records": business_count,
            },
            "storage": table_counts,
        }

        cache.set(cache_key, overview, timeout=cls.CACHE_TIMEOUT)
        return overview

    # ========================================================================
    # Ingestion Rate Graph
    # ========================================================================

    @classmethod
    async def aget_ingestion_rate(cls, hours: int = 24) -> dict[str, Any]:
        """
        Get ingestion rate data points for charting.

        Args:
            hours: Number of hours to look back.

        Returns:
            dict: Hourly ingestion counts.
        """
        cache_key = f"{cls.CACHE_PREFIX}ingestion_rate:{hours}h"
        cached = cache.get(cache_key)
        if cached:
            return cached

        now = timezone.now()
        data_points = []

        for i in range(hours, 0, -1):
            hour_start = now - timedelta(hours=i)
            hour_end = now - timedelta(hours=i - 1)
            count = await Metric.objects.filter(
                timestamp__gte=hour_start,
                timestamp__lt=hour_end,
            ).acount()
            data_points.append({
                "hour": hour_start.isoformat(),
                "count": count,
            })

        result = {
            "generated_at": now.isoformat(),
            "hours": hours,
            "data_points": data_points,
            "total": sum(dp["count"] for dp in data_points),
        }

        cache.set(cache_key, result, timeout=cls.CACHE_TIMEOUT)
        return result

    # ========================================================================
    # Query Latency Distribution
    # ========================================================================

    @classmethod
    async def aget_query_latency_distribution(cls, hours: int = 24) -> dict[str, Any]:
        """
        Get query latency distribution from PerformanceMetric data.

        Args:
            hours: Number of hours to look back.

        Returns:
            dict: Latency percentiles and distribution.
        """
        cache_key = f"{cls.CACHE_PREFIX}latency_dist:{hours}h"
        cached = cache.get(cache_key)
        if cached:
            return cached

        now = timezone.now()
        since = now - timedelta(hours=hours)

        # Get aggregated latency stats
        from django.db.models import Max, Min, Avg

        stats = await PerformanceMetric.objects.filter(timestamp__gte=since).aaggregate(
            avg_latency=Avg("response_time_ms"),
            max_latency=Max("response_time_ms"),
            min_latency=Min("response_time_ms"),
            total_requests=Count("id"),
        )

        # Get latency buckets
        buckets = [
            (0, 50, "0-50ms"),
            (50, 100, "50-100ms"),
            (100, 250, "100-250ms"),
            (250, 500, "250-500ms"),
            (500, 1000, "500-1000ms"),
            (1000, 5000, "1000-5000ms"),
            (5000, 999999, "5000ms+"),
        ]

        distribution = []
        for low, high, label in buckets:
            count = await PerformanceMetric.objects.filter(
                timestamp__gte=since,
                response_time_ms__gte=low,
                response_time_ms__lt=high,
            ).acount()
            distribution.append({
                "bucket": label,
                "count": count,
                "percentage": round((count / stats["total_requests"] * 100), 2) if stats["total_requests"] else 0,
            })

        result = {
            "generated_at": now.isoformat(),
            "hours": hours,
            "stats": {
                "avg_latency_ms": round(stats["avg_latency"], 2) if stats["avg_latency"] else 0,
                "max_latency_ms": stats["max_latency"] or 0,
                "min_latency_ms": stats["min_latency"] or 0,
                "total_requests": stats["total_requests"],
            },
            "distribution": distribution,
        }

        cache.set(cache_key, result, timeout=cls.CACHE_TIMEOUT)
        return result

    # ========================================================================
    # Error Rate by Endpoint
    # ========================================================================

    @classmethod
    async def aget_error_rate_by_endpoint(cls, hours: int = 24) -> dict[str, Any]:
        """
        Get error rate breakdown by API endpoint.

        Args:
            hours: Number of hours to look back.

        Returns:
            dict: Per-endpoint error rates.
        """
        cache_key = f"{cls.CACHE_PREFIX}error_rate:{hours}h"
        cached = cache.get(cache_key)
        if cached:
            return cached

        now = timezone.now()
        since = now - timedelta(hours=hours)

        # Get all endpoints with errors
        from asgiref.sync import sync_to_async

        @sync_to_async
        def get_endpoint_stats():
            endpoints = (
                PerformanceMetric.objects.filter(timestamp__gte=since)
                .values("endpoint")
                .annotate(
                    total=Count("id"),
                    errors=Count("id", filter=Q(status_code__gte=400)),
                    avg_latency=Avg("response_time_ms"),
                )
                .order_by("-errors")
            )
            return list(endpoints)

        endpoint_stats = await get_endpoint_stats()

        result = {
            "generated_at": now.isoformat(),
            "hours": hours,
            "endpoints": [
                {
                    "endpoint": ep["endpoint"],
                    "total_requests": ep["total"],
                    "errors": ep["errors"],
                    "error_rate": round((ep["errors"] / ep["total"] * 100), 2) if ep["total"] else 0,
                    "avg_latency_ms": round(ep["avg_latency"], 2) if ep["avg_latency"] else 0,
                }
                for ep in endpoint_stats
            ],
        }

        cache.set(cache_key, result, timeout=cls.CACHE_TIMEOUT)
        return result

    # ========================================================================
    # Storage Growth by Table
    # ========================================================================

    @classmethod
    async def _aget_table_counts(cls) -> dict[str, int]:
        """Get row counts for all analytics tables."""
        from asgiref.sync import sync_to_async

        @sync_to_async
        def get_counts():
            return {
                "metrics": Metric.objects.count(),
                "user_activity": UserActivity.objects.count(),
                "performance_metrics": PerformanceMetric.objects.count(),
                "business_metrics": BusinessMetric.objects.count(),
                "alerts": Alert.objects.count(),
            }

        return await get_counts()

    # ========================================================================
    # Cache Hit/Miss Rates
    # ========================================================================

    @classmethod
    async def aget_cache_stats(cls) -> dict[str, Any]:
        """
        Get cache hit/miss rates for analytics queries.

        Returns:
            dict: Cache statistics.
        """
        cache_key = f"{cls.CACHE_PREFIX}cache_stats"
        cached = cache.get(cache_key)
        if cached:
            return cached

        # Try to get Redis info
        try:
            from django_redis import get_redis_connection

            redis_conn = get_redis_connection("default")
            info = redis_conn.info("stats")
            hits = info.get("keyspace_hits", 0)
            misses = info.get("keyspace_misses", 0)
            total = hits + misses
            hit_rate = round((hits / total * 100), 2) if total else 0

            result = {
                "generated_at": timezone.now().isoformat(),
                "hits": hits,
                "misses": misses,
                "hit_rate": hit_rate,
                "total_requests": total,
            }
        except Exception:
            result = {
                "generated_at": timezone.now().isoformat(),
                "hits": 0,
                "misses": 0,
                "hit_rate": 0,
                "total_requests": 0,
                "note": "Redis stats unavailable",
            }

        cache.set(cache_key, result, timeout=cls.CACHE_TIMEOUT)
        return result
