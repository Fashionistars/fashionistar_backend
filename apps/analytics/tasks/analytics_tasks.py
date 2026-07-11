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
        from apps.analytics.workflows.user_behavior import UserBehaviorWorkflow

        workflow = UserBehaviorWorkflow()
        report = workflow.execute({"user_id": user_id, "days": days})

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
        from apps.analytics.workflows.product_performance import ProductPerformanceWorkflow

        workflow = ProductPerformanceWorkflow()
        report = workflow.execute({"product_id": product_id, "days": days})

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
    bind=True,
    name="apps.analytics.tasks.analytics_tasks.run_vendor_analytics",
    queue="analytics",
    max_retries=2,
    soft_time_limit=120,
    time_limit=150,
    ignore_result=False,
)
def run_vendor_analytics(self, vendor_id: int, days: int = 30) -> dict:
    """
    Analyse a single vendor's performance over the last N days.

    Args:
        vendor_id: Vendor PK
        days:      Lookback window (default: 30)

    Returns:
        dict: Vendor performance report
    """
    logger.info("[run_vendor_analytics] vendor_id=%s days=%d", vendor_id, days)

    try:
        from apps.analytics.workflows.vendor_performance import VendorPerformanceWorkflow

        workflow = VendorPerformanceWorkflow()
        report = workflow.execute({"vendor_id": vendor_id, "days": days})

        logger.info("[run_vendor_analytics] DONE vendor=%s", vendor_id)
        return report

    except Exception as exc:
        logger.exception("[run_vendor_analytics] FAILED vendor=%s", vendor_id)
        raise self.retry(exc=exc, countdown=60)


@shared_task(
    bind=True,
    name="apps.analytics.tasks.analytics_tasks.run_realtime_analytics",
    queue="analytics",
    max_retries=1,
    soft_time_limit=30,
    time_limit=60,
    ignore_result=False,
)
def run_realtime_analytics(self) -> dict:
    """
    Generate a lightweight real-time analytics snapshot.

    Returns:
        dict: Real-time metrics snapshot cached at analytics:realtime:snapshot
    """
    logger.info("[run_realtime_analytics] Starting real-time snapshot")

    try:
        import json
        from datetime import timedelta

        from django.core.cache import cache
        from django.utils import timezone

        from apps.analytics.services import AnalyticsService

        service = AnalyticsService()
        since = timezone.now() - timedelta(minutes=5)
        snapshot = {
            "generated_at": timezone.now().isoformat(),
            "recent_metrics_count": getattr(service, "_metrics_count", 0),
            "window_start": since.isoformat(),
        }

        cache_key = "analytics:realtime:snapshot"
        cache.set(cache_key, json.dumps(snapshot, default=str), timeout=60)

        logger.info("[run_realtime_analytics] DONE")
        return snapshot

    except Exception as exc:
        logger.exception("[run_realtime_analytics] FAILED")
        raise self.retry(exc=exc, countdown=30)


@shared_task(
    name="apps.analytics.tasks.analytics_tasks.cleanup_expired_data",
    queue="analytics",
    soft_time_limit=300,
    time_limit=360,
    ignore_result=False,
)
def cleanup_expired_data() -> dict:
    """
    Delete analytics records older than their configured retention period.

    Uses per-model retention days from ANALYTICS_SETTINGS['DATA_RETENTION']:
      - Metric:              METRICS_DAYS (default 30)
      - UserActivity:        USER_ACTIVITY_DAYS (default 90)
      - PerformanceMetric:   PERFORMANCE_METRICS_DAYS (default 30)
      - BusinessMetric:      BUSINESS_METRICS_DAYS (default 365)
      - Alert:               ALERTS_DAYS (default 90)

    Returns:
        dict: Summary of deleted counts per model.
    """
    from datetime import timedelta
    from django.utils import timezone
    from apps.analytics.models import Metric, UserActivity, PerformanceMetric, BusinessMetric, Alert
    from apps.analytics.settings import ANALYTICS_SETTINGS

    retention = ANALYTICS_SETTINGS["DATA_RETENTION"]
    now = timezone.now()
    results = {}

    model_configs = [
        ("metrics", Metric, retention["METRICS_DAYS"], "timestamp"),
        ("user_activity", UserActivity, retention["USER_ACTIVITY_DAYS"], "timestamp"),
        ("performance_metrics", PerformanceMetric, retention["PERFORMANCE_METRICS_DAYS"], "timestamp"),
        ("business_metrics", BusinessMetric, retention["BUSINESS_METRICS_DAYS"], "period_end"),
        ("alerts", Alert, retention["ALERTS_DAYS"], "fired_at"),
    ]

    for label, model, days, field in model_configs:
        cutoff = now - timedelta(days=days)
        try:
            deleted, _ = model.objects.filter(**{f"{field}__lt": cutoff}).delete()
            results[label] = {"deleted": deleted, "cutoff": cutoff.isoformat(), "retention_days": days}
            logger.info("[cleanup_expired_data] %s: deleted %d records older than %s", label, deleted, cutoff.isoformat())
        except Exception as exc:
            logger.error("[cleanup_expired_data] %s failed: %s", label, exc)
            results[label] = {"error": str(exc)}

    return {"status": "success", "results": results}


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
