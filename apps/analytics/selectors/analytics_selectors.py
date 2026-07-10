# apps/analytics/selectors/analytics_selectors.py
"""
Selector layer for Analytics domain.
Follows vendor pattern with dual sync/async methods for read-only data fetching.
"""

import asyncio
from typing import List, Dict, Any, Optional
from datetime import timedelta
from django.utils import timezone

from apps.analytics.models import Metric, UserActivity, PerformanceMetric, BusinessMetric, Alert


# ============================================================================
# Sync Selectors (Thin wrappers for backward compatibility)
# ============================================================================

def get_metrics(
    metric_name: str = None,
    metric_type: str = None,
    date_from=None,
    date_to=None,
    limit: int = 100,
) -> List[Metric]:
    """Get metrics with optional name/type/date filtering (sync)."""
    queryset = Metric.objects.all()
    if metric_name:
        queryset = queryset.filter(name=metric_name)
    if metric_type:
        queryset = queryset.filter(metric_type=metric_type)
    if date_from:
        queryset = queryset.filter(timestamp__gte=date_from)
    if date_to:
        queryset = queryset.filter(timestamp__lte=date_to)
    return list(queryset.order_by('-timestamp')[:limit])


def get_user_activity(
    user_id: str = None,
    action: str = None,
    date_from=None,
    date_to=None,
    limit: int = 100,
) -> List[UserActivity]:
    """Get user activity with optional user/action/date filtering (sync)."""
    queryset = UserActivity.objects.all()
    if user_id:
        queryset = queryset.filter(user_id=user_id)
    if action:
        queryset = queryset.filter(action=action)
    if date_from:
        queryset = queryset.filter(timestamp__gte=date_from)
    if date_to:
        queryset = queryset.filter(timestamp__lte=date_to)
    return list(queryset.order_by('-timestamp')[:limit])


def get_performance_metrics(
    endpoint: str = None,
    date_from=None,
    date_to=None,
    limit: int = 100,
) -> List[PerformanceMetric]:
    """Get performance metrics with optional endpoint/date filtering (sync)."""
    queryset = PerformanceMetric.objects.all()
    if endpoint:
        queryset = queryset.filter(endpoint=endpoint)
    if date_from:
        queryset = queryset.filter(timestamp__gte=date_from)
    if date_to:
        queryset = queryset.filter(timestamp__lte=date_to)
    return list(queryset.order_by('-timestamp')[:limit])


def get_business_metrics(
    metric_name: str = None,
    period_start=None,
    period_end=None,
    limit: int = 100,
) -> List[BusinessMetric]:
    """Get business metrics with optional name/period filtering (sync)."""
    queryset = BusinessMetric.objects.all()
    if metric_name:
        queryset = queryset.filter(metric_name=metric_name)
    if period_start:
        queryset = queryset.filter(period_start__gte=period_start)
    if period_end:
        queryset = queryset.filter(period_end__lte=period_end)
    return list(queryset.order_by('-period_start')[:limit])


def get_alerts(
    status: str = None, severity: str = None, limit: int = 50
) -> List[Alert]:
    """Get alerts by status/severity (sync)."""
    queryset = Alert.objects.all()
    if status:
        queryset = queryset.filter(status=status)
    if severity:
        queryset = queryset.filter(rule__severity=severity)
    return list(queryset.order_by('-fired_at')[:limit])


# ============================================================================
# Async Selectors (Native Django 6.0 async ORM)
# ============================================================================

async def aget_metrics(
    metric_name: str = None,
    metric_type: str = None,
    date_from=None,
    date_to=None,
    limit: int = 100,
) -> List[Metric]:
    """Get metrics with optional name/type/date filtering (async)."""
    queryset = Metric.objects.all()
    if metric_name:
        queryset = queryset.filter(name=metric_name)
    if metric_type:
        queryset = queryset.filter(metric_type=metric_type)
    if date_from:
        queryset = queryset.filter(timestamp__gte=date_from)
    if date_to:
        queryset = queryset.filter(timestamp__lte=date_to)
    return [m async for m in queryset.order_by('-timestamp')[:limit]]


async def aget_user_activity(
    user_id: str = None,
    action: str = None,
    date_from=None,
    date_to=None,
    limit: int = 100,
) -> List[UserActivity]:
    """Get user activity with optional user/action/date filtering (async)."""
    queryset = UserActivity.objects.all()
    if user_id:
        queryset = queryset.filter(user_id=user_id)
    if action:
        queryset = queryset.filter(action=action)
    if date_from:
        queryset = queryset.filter(timestamp__gte=date_from)
    if date_to:
        queryset = queryset.filter(timestamp__lte=date_to)
    return [a async for a in queryset.order_by('-timestamp')[:limit]]


async def aget_performance_metrics(
    endpoint: str = None,
    date_from=None,
    date_to=None,
    limit: int = 100,
) -> List[PerformanceMetric]:
    """Get performance metrics with optional endpoint/date filtering (async)."""
    queryset = PerformanceMetric.objects.all()
    if endpoint:
        queryset = queryset.filter(endpoint=endpoint)
    if date_from:
        queryset = queryset.filter(timestamp__gte=date_from)
    if date_to:
        queryset = queryset.filter(timestamp__lte=date_to)
    return [p async for p in queryset.order_by('-timestamp')[:limit]]


async def aget_business_metrics(
    metric_name: str = None,
    period_start=None,
    period_end=None,
    limit: int = 100,
) -> List[BusinessMetric]:
    """Get business metrics with optional name/period filtering (async)."""
    queryset = BusinessMetric.objects.all()
    if metric_name:
        queryset = queryset.filter(metric_name=metric_name)
    if period_start:
        queryset = queryset.filter(period_start__gte=period_start)
    if period_end:
        queryset = queryset.filter(period_end__lte=period_end)
    return [b async for b in queryset.order_by('-period_start')[:limit]]


async def aget_alerts(
    status: str = None, severity: str = None, limit: int = 50
) -> List[Alert]:
    """Get alerts by status/severity (async)."""
    queryset = Alert.objects.all()
    if status:
        queryset = queryset.filter(status=status)
    if severity:
        queryset = queryset.filter(rule__severity=severity)
    return [a async for a in queryset.order_by('-fired_at')[:limit]]


# ============================================================================
# Parallel Loading Selectors
# ============================================================================

async def aget_analytics_dashboard_parallel(
    user_id: Optional[str] = None,
    date_from=None,
    date_to=None,
) -> Dict[str, Any]:
    """
    Get analytics dashboard data in parallel using asyncio.gather.
    This is the primary async dashboard data fetcher.
    """
    tasks = [
        aget_performance_metrics(date_from=date_from, date_to=date_to, limit=50),
        aget_business_metrics(period_start=date_from, period_end=date_to, limit=50),
        aget_alerts(status='firing', limit=10),
    ]

    if user_id:
        tasks.append(aget_user_activity(user_id=user_id, date_from=date_from, date_to=date_to, limit=50))

    results = await asyncio.gather(*tasks, return_exceptions=True)

    performance_metrics = results[0] if not isinstance(results[0], Exception) else []
    business_metrics = results[1] if not isinstance(results[1], Exception) else []
    firing_alerts = results[2] if not isinstance(results[2], Exception) else []

    if user_id:
        user_activities = results[3] if not isinstance(results[3], Exception) else []
    else:
        user_activities = []

    avg_response_time = 0
    if performance_metrics:
        avg_response_time = sum(m.response_time_ms for m in performance_metrics) / len(performance_metrics)

    return {
        'performance_metrics': performance_metrics,
        'business_metrics': business_metrics,
        'alerts': firing_alerts,
        'user_activities': user_activities,
        'avg_response_time_ms': avg_response_time,
        'performance_count': len(performance_metrics),
        'business_count': len(business_metrics),
        'alert_count': len(firing_alerts),
        'activity_count': len(user_activities),
    }


async def aget_performance_dashboard_parallel(hours: int = 24) -> Dict[str, Any]:
    """
    Get performance-focused dashboard data in parallel.
    """
    now = timezone.now()
    since = now - timedelta(hours=hours)

    tasks = [
        aget_performance_metrics(date_from=since, date_to=now, limit=100),
        PerformanceMetric.aget_slow_queries(threshold_ms=500, date_from=since, date_to=now, limit=20),
        PerformanceMetric.aget_performance_summary(since, now),
    ]

    results = await asyncio.gather(*tasks, return_exceptions=True)

    performance_metrics = results[0] if not isinstance(results[0], Exception) else []
    slow_queries = results[1] if not isinstance(results[1], Exception) else []
    summary = results[2] if not isinstance(results[2], Exception) else {}

    total_requests = summary.get('total_requests', 0)
    error_count = summary.get('error_rate', 0)
    error_rate = (error_count / total_requests * 100) if total_requests else 0

    return {
        'performance_metrics': performance_metrics,
        'slow_queries': slow_queries,
        'summary': summary,
        'avg_response_time_ms': summary.get('avg_response_time', 0),
        'max_response_time_ms': summary.get('max_response_time', 0),
        'total_requests': total_requests,
        'error_rate_percent': error_rate,
        'slow_query_count': len(slow_queries),
    }


async def aget_alert_dashboard_parallel(limit: int = 100) -> Dict[str, Any]:
    """
    Get alert-focused dashboard data in parallel.
    """
    from apps.analytics.models import AlertRule

    tasks = [
        aget_alerts(status='firing', limit=limit),
        aget_alerts(status='resolved', limit=limit),
        AlertRule.aget_active_rules(),
    ]

    results = await asyncio.gather(*tasks, return_exceptions=True)

    firing = results[0] if not isinstance(results[0], Exception) else []
    resolved = results[1] if not isinstance(results[1], Exception) else []
    active_rules = results[2] if not isinstance(results[2], Exception) else []

    return {
        'firing_alerts': firing,
        'resolved_alerts': resolved,
        'active_rules': active_rules,
        'firing_count': len(firing),
        'resolved_count': len(resolved),
        'active_rule_count': len(active_rules),
    }
