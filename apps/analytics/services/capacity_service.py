"""
apps/analytics/services/capacity_service.py
============================================
Capacity planning and auto-scaling metrics service.

Tracks resource usage to inform scaling decisions:
  - DB connection pool utilization
  - Redis memory usage
  - Celery queue depth
  - Table row counts by partition
  - Rollup lag (seconds between now and last rollup window)

Exposes metrics to Prometheus via metrics_service.py and provides
a REST endpoint for capacity monitoring.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from django.core.cache import cache
from django.db import connection
from django.utils import timezone

from apps.analytics.models import (
    Alert,
    BusinessMetric,
    Metric,
    PerformanceMetric,
    UserActivity,
)

logger = logging.getLogger(__name__)


class CapacityService:
    """
    Monitor resource usage and inform scaling decisions.

    All methods return dicts suitable for JSON API responses or
    Prometheus metric export.
    """

    CACHE_PREFIX = "analytics:capacity:"
    CACHE_TIMEOUT = 30  # 30 seconds for near-real-time capacity data

    # ========================================================================
    # Full Capacity Report
    # ========================================================================

    @classmethod
    async def aget_capacity_report(cls) -> dict[str, Any]:
        """
        Get a comprehensive capacity report covering all monitored resources.

        Returns:
            dict: Full capacity metrics for all resources.
        """
        cache_key = f"{cls.CACHE_PREFIX}report"
        cached = cache.get(cache_key)
        if cached:
            return cached

        report = {
            "generated_at": timezone.now().isoformat(),
            "database": await cls._aget_db_stats(),
            "redis": await cls._aget_redis_stats(),
            "celery": await cls._aget_celery_stats(),
            "storage": await cls._aget_storage_stats(),
            "rollup_lag": await cls._aget_rollup_lag(),
        }

        cache.set(cache_key, report, timeout=cls.CACHE_TIMEOUT)
        return report

    # ========================================================================
    # Database Stats
    # ========================================================================

    @classmethod
    async def _aget_db_stats(cls) -> dict[str, Any]:
        """Get database connection pool statistics."""
        from asgiref.sync import sync_to_async

        @sync_to_async
        def get_db_stats():
            try:
                with connection.cursor() as cursor:
                    # Get connection count
                    cursor.execute("SELECT count(*) FROM pg_stat_activity WHERE state = 'active';")
                    active_connections = cursor.fetchone()[0]

                    cursor.execute("SELECT count(*) FROM pg_stat_activity;")
                    total_connections = cursor.fetchone()[0]

                    # Get database size
                    cursor.execute("SELECT pg_database_size(current_database());")
                    db_size_bytes = cursor.fetchone()[0]

                    # Get max connections setting
                    cursor.execute("SHOW max_connections;")
                    max_connections = int(cursor.fetchone()[0])

                    return {
                        "active_connections": active_connections,
                        "total_connections": total_connections,
                        "max_connections": max_connections,
                        "connection_utilization": round(
                            (total_connections / max_connections * 100), 2
                        ) if max_connections else 0,
                        "database_size_mb": round(db_size_bytes / (1024 * 1024), 2),
                    }
            except Exception as exc:
                logger.error("[CapacityService._aget_db_stats] Failed: %s", exc)
                return {"error": str(exc)}

        return await get_db_stats()

    # ========================================================================
    # Redis Stats
    # ========================================================================

    @classmethod
    async def _aget_redis_stats(cls) -> dict[str, Any]:
        """Get Redis memory and connection statistics."""
        from asgiref.sync import sync_to_async

        @sync_to_async
        def get_redis_stats():
            try:
                from django_redis import get_redis_connection

                redis_conn = get_redis_connection("default")
                info = redis_conn.info("memory")
                clients_info = redis_conn.info("clients")

                used_memory = info.get("used_memory", 0)
                max_memory = info.get("maxmemory", 0)
                memory_utilization = (
                    round((used_memory / max_memory * 100), 2) if max_memory else 0
                )

                return {
                    "used_memory_mb": round(used_memory / (1024 * 1024), 2),
                    "max_memory_mb": round(max_memory / (1024 * 1024), 2) if max_memory else 0,
                    "memory_utilization": memory_utilization,
                    "connected_clients": clients_info.get("connected_clients", 0),
                    "blocked_clients": clients_info.get("blocked_clients", 0),
                }
            except Exception as exc:
                logger.error("[CapacityService._aget_redis_stats] Failed: %s", exc)
                return {"error": str(exc)}

        return await get_redis_stats()

    # ========================================================================
    # Celery Queue Stats
    # ========================================================================

    @classmethod
    async def _aget_celery_stats(cls) -> dict[str, Any]:
        """Get Celery queue depth and worker statistics."""
        from asgiref.sync import sync_to_async

        @sync_to_async
        def get_celery_stats():
            try:
                from backend.celery import app as celery_app

                inspect = celery_app.control.inspect(timeout=3)
                active = inspect.active()
                scheduled = inspect.scheduled()
                reserved = inspect.reserved()

                active_count = sum(len(tasks) for tasks in (active or {}).values())
                scheduled_count = sum(len(tasks) for tasks in (scheduled or {}).values())
                reserved_count = sum(len(tasks) for tasks in (reserved or {}).values())

                worker_count = len(active or {})

                return {
                    "active_tasks": active_count,
                    "scheduled_tasks": scheduled_count,
                    "reserved_tasks": reserved_count,
                    "total_queue_depth": active_count + scheduled_count + reserved_count,
                    "active_workers": worker_count,
                }
            except Exception as exc:
                logger.error("[CapacityService._aget_celery_stats] Failed: %s", exc)
                return {"error": str(exc)}

        return await get_celery_stats()

    # ========================================================================
    # Storage Stats (Table Row Counts)
    # ========================================================================

    @classmethod
    async def _aget_storage_stats(cls) -> dict[str, Any]:
        """Get table row counts and approximate sizes."""
        from asgiref.sync import sync_to_async

        @sync_to_async
        def get_storage_stats():
            try:
                with connection.cursor() as cursor:
                    tables = [
                        "analytics_metric",
                        "analytics_useractivity",
                        "analytics_performancemetric",
                        "analytics_businessmetric",
                        "analytics_alertrule",
                        "analytics_alert",
                    ]

                    stats = {}
                    for table in tables:
                        cursor.execute(f"SELECT count(*) FROM {table};")
                        count = cursor.fetchone()[0]
                        cursor.execute(
                            f"SELECT pg_total_relation_size('{table}');"
                        )
                        size_bytes = cursor.fetchone()[0]
                        stats[table] = {
                            "row_count": count,
                            "size_mb": round(size_bytes / (1024 * 1024), 2),
                        }

                    return stats
            except Exception as exc:
                logger.error("[CapacityService._aget_storage_stats] Failed: %s", exc)
                return {"error": str(exc)}

        return await get_storage_stats()

    # ========================================================================
    # Rollup Lag
    # ========================================================================

    @classmethod
    async def _aget_rollup_lag(cls) -> dict[str, Any]:
        """
        Calculate the lag between now and the last rollup window.

        Large lag indicates aggregation tasks are falling behind.
        """
        from asgiref.sync import sync_to_async

        @sync_to_async
        def get_rollup_lag():
            now = timezone.now()

            # Check latest metric timestamp
            latest_metric = Metric.objects.order_by("-timestamp").first()
            metric_lag = (now - latest_metric.timestamp).total_seconds() if latest_metric else None

            # Check latest performance metric
            latest_perf = PerformanceMetric.objects.order_by("-timestamp").first()
            perf_lag = (now - latest_perf.timestamp).total_seconds() if latest_perf else None

            return {
                "metric_lag_seconds": round(metric_lag, 2) if metric_lag else None,
                "performance_metric_lag_seconds": round(perf_lag, 2) if perf_lag else None,
                "threshold_seconds": 300,  # 5 minutes
                "status": "healthy" if (not metric_lag or metric_lag < 300) else "lagging",
            }

        return await get_rollup_lag()

    # ========================================================================
    # Prometheus Export
    # ========================================================================

    @classmethod
    def export_prometheus_metrics(cls) -> str:
        """
        Export capacity metrics in Prometheus text format.

        Returns:
            str: Prometheus-formatted metrics.
        """
        from apps.analytics.services.metrics_service import get_metrics_service

        metrics_service = get_metrics_service()

        # Get cached report (sync context — use cached data)
        report = cache.get(f"{cls.CACHE_PREFIX}report")
        if not report:
            return "# Capacity metrics not yet available\n"

        lines = []

        # Database metrics
        db = report.get("database", {})
        if "error" not in db:
            lines.append(f"# TYPE analytics_db_active_connections gauge")
            lines.append(f"analytics_db_active_connections {db.get('active_connections', 0)}")
            lines.append(f"analytics_db_total_connections {db.get('total_connections', 0)}")
            lines.append(f"analytics_db_connection_utilization {db.get('connection_utilization', 0)}")
            lines.append(f"analytics_db_size_mb {db.get('database_size_mb', 0)}")

        # Redis metrics
        redis = report.get("redis", {})
        if "error" not in redis:
            lines.append(f"# TYPE analytics_redis_memory_utilization gauge")
            lines.append(f"analytics_redis_memory_utilization {redis.get('memory_utilization', 0)}")
            lines.append(f"analytics_redis_used_memory_mb {redis.get('used_memory_mb', 0)}")
            lines.append(f"analytics_redis_connected_clients {redis.get('connected_clients', 0)}")

        # Celery metrics
        celery = report.get("celery", {})
        if "error" not in celery:
            lines.append(f"# TYPE analytics_celery_queue_depth gauge")
            lines.append(f"analytics_celery_queue_depth {celery.get('total_queue_depth', 0)}")
            lines.append(f"analytics_celery_active_workers {celery.get('active_workers', 0)}")

        # Rollup lag
        rollup = report.get("rollup_lag", {})
        if rollup.get("metric_lag_seconds") is not None:
            lines.append(f"# TYPE analytics_rollup_lag_seconds gauge")
            lines.append(f"analytics_rollup_lag_seconds {rollup['metric_lag_seconds']}")

        return "\n".join(lines) + "\n"
