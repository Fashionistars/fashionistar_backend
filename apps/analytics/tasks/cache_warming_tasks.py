"""
apps/analytics/tasks/cache_warming_tasks.py
============================================
Celery tasks for warming Redis cache with pre-computed analytics data.

Tasks:
  - warm_dashboard_cache: Pre-compute dashboard data every 5 minutes
  - refresh_materialized_views: Refresh materialized views every hour
  - warm_query_builder_cache: Pre-compute common query templates every 10 minutes

Queue: "analytics"
"""

from __future__ import annotations

import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(
    name="apps.analytics.tasks.cache_warming_tasks.warm_dashboard_cache",
    queue="analytics",
    soft_time_limit=120,
    time_limit=150,
    ignore_result=True,
)
def warm_dashboard_cache() -> None:
    """
    Pre-compute and cache dashboard data for fast admin panel rendering.

    Runs every 5 minutes via Celery Beat.
    """
    import asyncio
    from apps.analytics.services.dashboard_service import DashboardService

    logger.info("[warm_dashboard_cache] Starting cache warming")

    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            # Pre-compute all dashboard views
            loop.run_until_complete(DashboardService.aget_system_overview())
            loop.run_until_complete(DashboardService.aget_ingestion_rate(hours=24))
            loop.run_until_complete(DashboardService.aget_query_latency_distribution(hours=24))
            loop.run_until_complete(DashboardService.aget_error_rate_by_endpoint(hours=24))
            loop.run_until_complete(DashboardService.aget_cache_stats())
        finally:
            loop.close()

        logger.info("[warm_dashboard_cache] DONE")
    except Exception as exc:
        logger.exception("[warm_dashboard_cache] FAILED: %s", exc)


@shared_task(
    name="apps.analytics.tasks.cache_warming_tasks.refresh_materialized_views",
    queue="analytics",
    soft_time_limit=300,
    time_limit=360,
    ignore_result=True,
)
def refresh_materialized_views() -> None:
    """
    Refresh all materialized views for pre-computed aggregations.

    Runs every hour via Celery Beat.
    """
    from apps.analytics.database.materialized_views import MaterializedViewManager

    logger.info("[refresh_materialized_views] Starting refresh")

    try:
        results = MaterializedViewManager.refresh_all()
        succeeded = sum(1 for v in results.values() if v)
        failed = sum(1 for v in results.values() if not v)
        logger.info(
            "[refresh_materialized_views] DONE — Succeeded=%d Failed=%d",
            succeeded,
            failed,
        )
    except Exception as exc:
        logger.exception("[refresh_materialized_views] FAILED: %s", exc)


@shared_task(
    name="apps.analytics.tasks.cache_warming_tasks.warm_query_builder_cache",
    queue="analytics",
    soft_time_limit=120,
    time_limit=150,
    ignore_result=True,
)
def warm_query_builder_cache() -> None:
    """
    Pre-compute and cache common query builder templates.

    Runs every 10 minutes via Celery Beat.
    """
    from apps.analytics.services.query_builder import AnalyticsQueryBuilder

    logger.info("[warm_query_builder_cache] Starting cache warming")

    templates = AnalyticsQueryBuilder.list_templates()
    for template_name in templates:
        try:
            AnalyticsQueryBuilder.execute_template(template_name)
            logger.debug("[warm_query_builder_cache] Warmed template '%s'", template_name)
        except Exception as exc:
            logger.warning("[warm_query_builder_cache] Template '%s' failed: %s", template_name, exc)

    logger.info("[warm_query_builder_cache] DONE — Warmed %d templates", len(templates))


@shared_task(
    name="apps.analytics.tasks.cache_warming_tasks.warm_capacity_cache",
    queue="analytics",
    soft_time_limit=60,
    time_limit=90,
    ignore_result=True,
)
def warm_capacity_cache() -> None:
    """
    Pre-compute and cache capacity planning metrics.

    Runs every 2 minutes via Celery Beat for near-real-time capacity data.
    """
    import asyncio
    from apps.analytics.services.capacity_service import CapacityService

    logger.info("[warm_capacity_cache] Starting")

    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(CapacityService.aget_capacity_report())
        finally:
            loop.close()

        logger.info("[warm_capacity_cache] DONE")
    except Exception as exc:
        logger.exception("[warm_capacity_cache] FAILED: %s", exc)
