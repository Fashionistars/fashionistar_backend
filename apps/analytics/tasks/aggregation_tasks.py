# apps/analytics/tasks/aggregation_tasks.py
"""
Metric aggregation Celery tasks.

Rolls up analytics metrics into coarser time windows and caches results for
fast dashboard reads. Tasks are routed to the analytics queue.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta

from celery import shared_task
from django.core.cache import cache
from django.utils import timezone

from apps.analytics.services.metrics_service import get_metrics_service
from apps.audit_logs.services.analytics.analytics_audit import AnalyticsAuditService
from apps.analytics.services.sentry_service import AnalyticsSentryService

logger = logging.getLogger(__name__)
metrics_service = get_metrics_service()


def _get_window_floor(interval_minutes: int) -> datetime:
    """Return the start of the current N-minute window."""
    now = timezone.now()
    return now.replace(
        minute=(now.minute // interval_minutes) * interval_minutes,
        second=0,
        microsecond=0,
    )


async def _aggregate_metrics(window_start: datetime, window_end: datetime):
    """Aggregate Metric and PerformanceMetric records within a window."""
    from apps.analytics.models import Metric, PerformanceMetric
    from django.db.models import Avg, Count, Q

    metric_stats = await Metric.objects.filter(
        timestamp__gte=window_start, timestamp__lt=window_end
    ).aaggregate(count=Count('id'), avg_value=Avg('value'))

    perf_stats = await PerformanceMetric.objects.filter(
        timestamp__gte=window_start, timestamp__lt=window_end
    ).aaggregate(
        count=Count('id'),
        avg_response_time=Avg('response_time_ms'),
        error_count=Count('id', filter=~Q(status_code__range=(200, 299))),
    )

    return {
        "metric_count": metric_stats.get('count', 0),
        "avg_metric_value": metric_stats.get('avg_value') or 0,
        "request_count": perf_stats.get('count', 0),
        "avg_response_time_ms": perf_stats.get('avg_response_time') or 0,
        "error_count": perf_stats.get('error_count', 0),
        "window_start": window_start.isoformat(),
        "window_end": window_end.isoformat(),
    }


def _run_rollup(window: str, interval_minutes: int, ttl: int, window_format: str) -> None:
    """Shared helper for a single rollup task."""
    logger.info("[rollup_%s] Starting aggregation", window)
    try:
        if window == "1d":
            end = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
            start = end - timedelta(days=1)
        else:
            end = _get_window_floor(interval_minutes)
            start = end - timedelta(minutes=interval_minutes)

        result = _run_async(_aggregate_metrics(start, end))
        cache_key = f"analytics:rollup:{window}:{end.strftime(window_format)}"
        cache.set(cache_key, json.dumps(result, default=str), timeout=ttl)

        metrics_service.record_aggregation(window=window)
        AnalyticsAuditService.log_metric_aggregation_executed(
            actor=None,
            aggregation_window=window,
            record_count=result.get("metric_count", 0) + result.get("request_count", 0),
        )
        logger.info("[rollup_%s] Cached %s", window, cache_key)
    except Exception as exc:
        logger.exception("[rollup_%s] failed: %s", window, exc)
        metrics_service.record_error(source=f"rollup_{window}")
        AnalyticsSentryService.capture_exception(
            exception=exc,
            context={"task": f"rollup_{window}"},
            tags={"domain": "analytics", "task": f"rollup_{window}"},
        )


@shared_task(
    name="apps.analytics.tasks.aggregation_tasks.rollup_1m",
    queue="analytics",
    ignore_result=True,
)
def rollup_1m() -> None:
    """Roll up analytics metrics for the last completed minute."""
    _run_rollup("1m", 1, 600, "%Y%m%d%H%M")


@shared_task(
    name="apps.analytics.tasks.aggregation_tasks.rollup_5m",
    queue="analytics",
    ignore_result=True,
)
def rollup_5m() -> None:
    """Roll up analytics metrics for the last completed 5-minute window."""
    _run_rollup("5m", 5, 1800, "%Y%m%d%H%M")


@shared_task(
    name="apps.analytics.tasks.aggregation_tasks.rollup_1h",
    queue="analytics",
    ignore_result=True,
)
def rollup_1h() -> None:
    """Roll up analytics metrics for the last completed hour."""
    _run_rollup("1h", 60, 7200, "%Y%m%d%H")


@shared_task(
    name="apps.analytics.tasks.aggregation_tasks.rollup_1d",
    queue="analytics",
    ignore_result=True,
)
def rollup_1d() -> None:
    """Roll up analytics metrics for the last completed day."""
    _run_rollup("1d", 1440, 86400, "%Y%m%d")


def _run_async(coro):
    """Run an async coroutine from a sync Celery task."""
    import asyncio
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)
