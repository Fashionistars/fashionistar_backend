"""
apps/analytics/database/materialized_views.py
===============================================
Materialized views for pre-computing common analytics aggregations.

Views:
  - daily_active_users (DAU)
  - daily_revenue (GMV)
  - hourly_error_rates
  - top_products_by_views
  - vendor_performance_summary

All views are refreshed via Celery Beat (see cache_warming_tasks.py).
"""

from __future__ import annotations

import logging

from django.db import connection

logger = logging.getLogger(__name__)


class MaterializedViewManager:
    """
    Manages creation, refresh, and querying of materialized views
    for analytics aggregations.
    """

    VIEWS = {
        "daily_active_users": """
            CREATE MATERIALIZED VIEW IF NOT EXISTS mv_daily_active_users AS
            SELECT
                DATE(timestamp) AS date,
                COUNT(DISTINCT user_id) AS active_users,
                COUNT(*) AS total_activities
            FROM analytics_useractivity
            GROUP BY DATE(timestamp)
            WITH DATA;
        """,
        "daily_revenue": """
            CREATE MATERIALIZED VIEW IF NOT EXISTS mv_daily_revenue AS
            SELECT
                DATE(period_start) AS date,
                metric_name,
                SUM(value) AS total_value,
                AVG(value) AS avg_value,
                COUNT(*) AS record_count
            FROM analytics_businessmetric
            WHERE metric_name LIKE '%revenue%'
            GROUP BY DATE(period_start), metric_name
            WITH DATA;
        """,
        "hourly_error_rates": """
            CREATE MATERIALIZED VIEW IF NOT EXISTS mv_hourly_error_rates AS
            SELECT
                DATE_TRUNC('hour', timestamp) AS hour,
                endpoint,
                method,
                COUNT(*) AS total_requests,
                COUNT(*) FILTER (WHERE status_code >= 400) AS error_count,
                AVG(response_time_ms) AS avg_response_time_ms
            FROM analytics_performancemetric
            GROUP BY DATE_TRUNC('hour', timestamp), endpoint, method
            WITH DATA;
        """,
        "top_products_by_views": """
            CREATE MATERIALIZED VIEW IF NOT EXISTS mv_top_products_by_views AS
            SELECT
                DATE(timestamp) AS date,
                resource_id AS product_id,
                COUNT(*) AS view_count
            FROM analytics_useractivity
            WHERE action = 'product_view' AND resource_id IS NOT NULL
            GROUP BY DATE(timestamp), resource_id
            ORDER BY view_count DESC
            WITH DATA;
        """,
        "vendor_performance_summary": """
            CREATE MATERIALIZED VIEW IF NOT EXISTS mv_vendor_performance_summary AS
            SELECT
                DATE(period_start) AS date,
                metric_name,
                SUM(value) AS total_value,
                AVG(value) AS avg_value
            FROM analytics_businessmetric
            WHERE metric_name LIKE 'vendor_%'
            GROUP BY DATE(period_start), metric_name
            WITH DATA;
        """,
    }

    @classmethod
    def create_all(cls) -> dict[str, bool]:
        """
        Create all materialized views.

        Returns:
            dict: Status of each view creation.
        """
        results = {}
        for view_name, sql in cls.VIEWS.items():
            try:
                with connection.cursor() as cursor:
                    cursor.execute(sql)
                    # Create unique index for refresh
                    cursor.execute(
                        f"CREATE UNIQUE INDEX IF NOT EXISTS idx_{view_name}_unique "
                        f"ON mv_{view_name} (1);"
                    )
                results[view_name] = True
                logger.info("[MaterializedViewManager] Created view '%s'", view_name)
            except Exception as exc:
                logger.error("[MaterializedViewManager] Failed to create '%s': %s", view_name, exc)
                results[view_name] = False

        return results

    @classmethod
    def refresh_all(cls) -> dict[str, bool]:
        """
        Refresh all materialized views concurrently.

        Returns:
            dict: Status of each refresh.
        """
        results = {}
        for view_name in cls.VIEWS:
            try:
                with connection.cursor() as cursor:
                    cursor.execute(f"REFRESH MATERIALIZED VIEW CONCURRENTLY mv_{view_name};")
                results[view_name] = True
                logger.info("[MaterializedViewManager] Refreshed view '%s'", view_name)
            except Exception as exc:
                logger.error("[MaterializedViewManager] Failed to refresh '%s': %s", view_name, exc)
                results[view_name] = False

        return results

    @classmethod
    def refresh_view(cls, view_name: str) -> bool:
        """
        Refresh a single materialized view.

        Args:
            view_name: Name of the view (without mv_ prefix).

        Returns:
            bool: True if refresh succeeded.
        """
        if view_name not in cls.VIEWS:
            raise ValueError(f"Unknown view: {view_name}. Available: {list(cls.VIEWS.keys())}")

        try:
            with connection.cursor() as cursor:
                cursor.execute(f"REFRESH MATERIALIZED VIEW CONCURRENTLY mv_{view_name};")
            logger.info("[MaterializedViewManager] Refreshed view '%s'", view_name)
            return True
        except Exception as exc:
            logger.error("[MaterializedViewManager] Failed to refresh '%s': %s", view_name, exc)
            return False

    @classmethod
    def drop_all(cls) -> dict[str, bool]:
        """
        Drop all materialized views.

        Returns:
            dict: Status of each drop.
        """
        results = {}
        for view_name in cls.VIEWS:
            try:
                with connection.cursor() as cursor:
                    cursor.execute(f"DROP MATERIALIZED VIEW IF EXISTS mv_{view_name} CASCADE;")
                results[view_name] = True
                logger.info("[MaterializedViewManager] Dropped view '%s'", view_name)
            except Exception as exc:
                logger.error("[MaterializedViewManager] Failed to drop '%s': %s", view_name, exc)
                results[view_name] = False

        return results

    @classmethod
    def query_view(cls, view_name: str, limit: int = 100) -> list[dict]:
        """
        Query a materialized view.

        Args:
            view_name: Name of the view (without mv_ prefix).
            limit: Maximum number of results.

        Returns:
            list[dict]: Query results as dicts.
        """
        if view_name not in cls.VIEWS:
            raise ValueError(f"Unknown view: {view_name}. Available: {list(cls.VIEWS.keys())}")

        try:
            with connection.cursor() as cursor:
                cursor.execute(f"SELECT * FROM mv_{view_name} LIMIT %s;", [limit])
                columns = [col[0] for col in cursor.description]
                rows = cursor.fetchall()
                return [dict(zip(columns, row)) for row in rows]
        except Exception as exc:
            logger.error("[MaterializedViewManager] Query failed for '%s': %s", view_name, exc)
            return []
