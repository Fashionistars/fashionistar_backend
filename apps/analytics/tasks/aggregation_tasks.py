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

logger = logging.getLogger(__name__)


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


@shared_task(
    name="apps.analytics.tasks.aggregation_tasks.rollup_1m",
    queue="analytics",
    ignore_result=True,
)
def rollup_1m() -> None:
    """Roll up analytics metrics for the last completed minute."""
    logger.info("[rollup_1m] Starting 1-minute aggregation")
    try:
        end = _get_window_floor(1)
        start = end - timedelta(minutes=1)
        result = _run_async(_aggregate_metrics(start, end))
        cache_key = f"analytics:rollup:1m:{end.strftime('%Y%m%d%H%M')}"
        cache.set(cache_key, json.dumps(result, default=str), timeout=600)
        logger.info("[rollup_1m] Cached %s", cache_key)
    except Exception as exc:
        logger.exception("[rollup_1m] failed: %s", exc)


@shared_task(
    name="apps.analytics.tasks.aggregation_tasks.rollup_5m",
    queue="analytics",
    ignore_result=True,
)
def rollup_5m() -> None:
    """Roll up analytics metrics for the last completed 5-minute window."""
    logger.info("[rollup_5m] Starting 5-minute aggregation")
    try:
        end = _get_window_floor(5)
        start = end - timedelta(minutes=5)
        result = _run_async(_aggregate_metrics(start, end))
        cache_key = f"analytics:rollup:5m:{end.strftime('%Y%m%d%H%M')}"
        cache.set(cache_key, json.dumps(result, default=str), timeout=1800)
        logger.info("[rollup_5m] Cached %s", cache_key)
    except Exception as exc:
        logger.exception("[rollup_5m] failed: %s", exc)


@shared_task(
    name="apps.analytics.tasks.aggregation_tasks.rollup_1h",
    queue="analytics",
    ignore_result=True,
)
def rollup_1h() -> None:
    """Roll up analytics metrics for the last completed hour."""
    logger.info("[rollup_1h] Starting 1-hour aggregation")
    try:
        end = _get_window_floor(60)
        start = end - timedelta(hours=1)
        result = _run_async(_aggregate_metrics(start, end))
        cache_key = f"analytics:rollup:1h:{end.strftime('%Y%m%d%H')}"
        cache.set(cache_key, json.dumps(result, default=str), timeout=7200)
        logger.info("[rollup_1h] Cached %s", cache_key)
    except Exception as exc:
        logger.exception("[rollup_1h] failed: %s", exc)


@shared_task(
    name="apps.analytics.tasks.aggregation_tasks.rollup_1d",
    queue="analytics",
    ignore_result=True,
)
def rollup_1d() -> None:
    """Roll up analytics metrics for the last completed day."""
    logger.info("[rollup_1d] Starting 1-day aggregation")
    try:
        end = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
        start = end - timedelta(days=1)
        result = _run_async(_aggregate_metrics(start, end))
        cache_key = f"analytics:rollup:1d:{end.strftime('%Y%m%d')}"
        cache.set(cache_key, json.dumps(result, default=str), timeout=86400)
        logger.info("[rollup_1d] Cached %s", cache_key)
    except Exception as exc:
        logger.exception("[rollup_1d] failed: %s", exc)


def _run_async(coro):
    """Run an async coroutine from a sync Celery task."""
    import asyncio
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)
