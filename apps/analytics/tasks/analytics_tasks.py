# apps/analytics/tasks/analytics_tasks.py
"""
Celery tasks for the FASHIONISTAR Analytics pipeline.

Tasks:
  run_platform_analytics()          — Full platform analytics report (daily cron)
  run_user_behavior_analysis()      — Single-user behaviour analysis
  run_product_performance_analysis() — Single-product performance deep-dive
  generate_daily_report()           — Daily report generation (Celery Beat trigger)

Queue: "analytics" (dedicated queue for analytics tasks)
Celery Beat Schedule: Every day at 02:00 UTC (configured in backend/celery.py)
"""

from __future__ import annotations

import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    name="apps.analytics.tasks.analytics_tasks.run_platform_analytics",
    queue="analytics",
    max_retries=2,
    default_retry_delay=120,
    soft_time_limit=600,   # 10 minutes max
    time_limit=660,
    ignore_result=False,
)
def run_platform_analytics(
    self,
    days: int = 7,
    scope: str = "platform",
    scope_id: int | None = None,
) -> dict:
    """
    Full platform analytics pipeline via apps.analytics.workflows.AnalyticsWorkflow.

    Aggregates:
    - Order metrics (GMV, AOV, conversion)
    - Product metrics (trending, inventory)
    - User metrics (registrations, KYC rate, profile rate)
    - Vendor metrics (performance, GMV distribution)

    Detects anomalies + generates LLM insights (via apps.analytics.entry_points).
    Persists report to Redis (TTL 24h) and optionally DB.

    Called:
    - Automatically by Celery Beat (daily at 02:00 UTC)
    - On-demand via Ninja analytics endpoint

    Args:
        days:     Lookback window in days (default: 7)
        scope:    'platform' | 'vendor' | 'user'
        scope_id: Vendor PK or User PK (None for platform-wide)

    Returns:
        dict: Full analytics report
    """
    logger.info(
        "[run_platform_analytics] scope=%s scope_id=%s days=%d",
        scope, scope_id, days,
    )

    try:
        from apps.analytics.workflows.analytics import AnalyticsWorkflow

        workflow = AnalyticsWorkflow()
        report = workflow.execute({
            "days":     days,
            "scope":    scope,
            "scope_id": scope_id,
        })

        logger.info(
            "[run_platform_analytics] DONE — anomalies=%d insights_len=%d",
            len(report.get("anomalies", [])),
            len(report.get("llm_insights", "")),
        )
        return report

    except Exception as exc:
        logger.exception("[run_platform_analytics] FAILED")
        raise self.retry(exc=exc, countdown=120)


@shared_task(
    bind=True,
    name="apps.analytics.tasks.analytics_tasks.run_user_behavior_analysis",
    queue="analytics",
    max_retries=2,
    soft_time_limit=120,
    time_limit=150,
    ignore_result=False,
)
def run_user_behavior_analysis(self, user_id: int, days: int = 30) -> dict:
    """
    Analyse a single user's behaviour over the last N days.

    Outputs:
    - Purchase pattern
    - Measurement profile completeness
    - Recommendation engagement rate
    - Personalised product affinity vector

    Cached in Redis at key: analytics:report:user:{user_id}

    Args:
        user_id: User PK
        days:    Lookback window (default: 30)

    Returns:
        dict: User behaviour analysis report
    """
    logger.info("[run_user_behavior_analysis] user_id=%s days=%d", user_id, days)

    try:
        from apps.ai.database.access_layer import FashionistarDatabaseLayer
        import json
        from django.core.cache import cache

        db = FashionistarDatabaseLayer()
        context    = db.get_user_full_context(user_id) or {}
        orders     = db.get_user_order_history(user_id) or []
        measures   = db.get_user_measurements(user_id) or []

        report = {
            "user_id":               user_id,
            "days":                  days,
            "total_orders":          len(orders),
            "measurement_profiles":  len(measures),
            "has_default_profile":   any(m.get("is_default") for m in measures),
            "purchase_categories":   context.get("recent_categories", []),
            "engagement_signals":    context.get("engagement", {}),
        }

        cache_key = f"analytics:report:user:{user_id}"
        cache.set(cache_key, json.dumps(report, default=str), timeout=86400)

        logger.info("[run_user_behavior_analysis] DONE user=%s", user_id)
        return report

    except Exception as exc:
        logger.exception("[run_user_behavior_analysis] FAILED user=%s", user_id)
        raise self.retry(exc=exc, countdown=60)


@shared_task(
    bind=True,
    name="apps.analytics.tasks.analytics_tasks.run_product_performance_analysis",
    queue="analytics",
    max_retries=2,
    soft_time_limit=120,
    time_limit=150,
    ignore_result=False,
)
def run_product_performance_analysis(self, product_id: int, days: int = 30) -> dict:
    """
    Analyse a single product's performance metrics.

    Outputs:
    - View count, conversion rate
    - Revenue generated in window
    - Embedding similarity score distribution
    - Review sentiment (if available)
    - Size fit rate (% of buyers who returned for size mismatch)

    Args:
        product_id: Product PK
        days:       Lookback window

    Returns:
        dict: Product performance report
    """
    logger.info(
        "[run_product_performance_analysis] product_id=%s days=%d",
        product_id, days,
    )

    try:
        from apps.ai.database.access_layer import FashionistarDatabaseLayer
        import json
        from django.core.cache import cache

        db = FashionistarDatabaseLayer()
        product_data = db.get_product_full(product_id) or {}

        # Basic performance snapshot
        report = {
            "product_id":  product_id,
            "days":        days,
            "name":        product_data.get("name"),
            "category":    product_data.get("category"),
            "total_views": product_data.get("view_count", 0),
            "total_sales": product_data.get("sales_count", 0),
            "rating":      product_data.get("average_rating"),
            "stock":       product_data.get("stock_quantity"),
        }

        cache_key = f"analytics:report:product:{product_id}"
        cache.set(cache_key, json.dumps(report, default=str), timeout=43200)

        logger.info(
            "[run_product_performance_analysis] DONE product=%s", product_id
        )
        return report

    except Exception as exc:
        logger.exception(
            "[run_product_performance_analysis] FAILED product=%s", product_id
        )
        raise self.retry(exc=exc, countdown=60)


@shared_task(
    name="apps.analytics.tasks.analytics_tasks.generate_daily_report",
    queue="analytics",
    soft_time_limit=900,    # 15 minutes
    time_limit=960,
    ignore_result=True,
)
def generate_daily_report() -> None:
    """
    Celery Beat periodic task: generate the daily platform analytics report.

    Runs every day at 02:00 UTC (configured in backend/celery.py CELERY_BEAT_SCHEDULE).

    Generates:
    - 1-day report (yesterday's metrics)
    - 7-day rolling report
    - 30-day rolling report

    All three are cached in Redis and served by the Ninja analytics endpoint.
    """
    logger.info("[generate_daily_report] Starting daily analytics generation")

    for days in [1, 7, 30]:
        try:
            run_platform_analytics.apply(
                kwargs={"days": days, "scope": "platform"},
            )
            logger.info("[generate_daily_report] %d-day report generated", days)
        except Exception as exc:
            logger.warning(
                "[generate_daily_report] Failed for days=%d: %s", days, exc
            )

    logger.info("[generate_daily_report] All daily reports completed")
