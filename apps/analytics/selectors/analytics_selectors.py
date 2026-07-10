# apps/analytics/selectors/analytics_selectors.py
"""
Selector layer for Analytics domain.
Follows vendor pattern with dual sync/async methods for read-only data fetching.
"""

import asyncio
from typing import List, Dict, Any, Optional
from datetime import timedelta
from django.utils import timezone

from apps.analytics.models import Metric, UserActivity, PerformanceMetric, BusinessMetric, AlertRule, Alert


# ============================================================================
# Sync Selectors (Thin wrappers for backward compatibility)
# ============================================================================

def get_metrics_by_name(name: str, limit: int = 100) -> List[Metric]:
    """Get metrics by name (sync)."""
    return list(Metric.objects.filter(name=name).order_by('-timestamp')[:limit])


def get_user_activities(user_id: str, limit: int = 100) -> List[UserActivity]:
    """Get user activities (sync)."""
    return list(UserActivity.objects.filter(user_id=user_id).order_by('-timestamp')[:limit])


def get_performance_metrics(hours: int = 24, limit: int = 100) -> List[PerformanceMetric]:
    """Get recent performance metrics (sync)."""
    since = timezone.now() - timedelta(hours=hours)
    return list(PerformanceMetric.objects.filter(timestamp__gte=since).order_by('-timestamp')[:limit])


def get_business_metrics(days: int = 30, limit: int = 100) -> List[BusinessMetric]:
    """Get recent business metrics (sync)."""
    since = timezone.now() - timedelta(days=days)
    return list(BusinessMetric.objects.filter(created_at__gte=since).order_by('-created_at')[:limit])


def get_firing_alerts(limit: int = 100) -> List[Alert]:
    """Get currently firing alerts (sync)."""
    return list(Alert.objects.filter(status='firing').order_by('-fired_at')[:limit])


# ============================================================================
# Async Selectors (Native Django 6.0 async ORM)
# ============================================================================

async def aget_metrics_by_name(name: str, limit: int = 100) -> List[Metric]:
    """Get metrics by name (async)."""
    return await Metric.aget_by_name(name, limit)


async def aget_user_activities(user_id: str, limit: int = 100) -> List[UserActivity]:
    """Get user activities (async)."""
    return await UserActivity.aget_by_user(user_id, limit)


async def aget_performance_metrics(hours: int = 24, limit: int = 100) -> List[PerformanceMetric]:
    """Get recent performance metrics (async)."""
    return await PerformanceMetric.aget_recent_metrics(hours, limit)


async def aget_business_metrics(days: int = 30, limit: int = 100) -> List[BusinessMetric]:
    """Get recent business metrics (async)."""
    return await BusinessMetric.aget_recent_metrics(days, limit)


async def aget_firing_alerts(limit: int = 100) -> List[Alert]:
    """Get currently firing alerts (async)."""
    return await Alert.aget_firing_alerts(limit)


async def aget_analytics_dashboard_parallel(user_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Get analytics dashboard data in parallel using asyncio.gather.
    This is the primary async dashboard data fetcher.
    """
    tasks = [
        aget_performance_metrics(hours=24, limit=50),
        aget_business_metrics(days=7, limit=50),
        aget_firing_alerts(limit=10),
    ]
    
    if user_id:
        tasks.append(aget_user_activities(user_id, limit=50))
    
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    performance_metrics = results[0] if not isinstance(results[0], Exception) else []
    business_metrics = results[1] if not isinstance(results[1], Exception) else []
    firing_alerts = results[2] if not isinstance(results[2], Exception) else []
    
    if user_id:
        user_activities = results[3] if not isinstance(results[3], Exception) else []
    else:
        user_activities = []
    
    # Calculate aggregates
    avg_response_time = 0
    if performance_metrics:
        avg_response_time = sum(m.response_time_ms for m in performance_metrics) / len(performance_metrics)
    
    return {
        'performance_metrics': performance_metrics,
        'business_metrics': business_metrics,
        'firing_alerts': firing_alerts,
        'user_activities': user_activities,
        'avg_response_time_ms': avg_response_time,
        'performance_count': len(performance_metrics),
        'business_count': len(business_metrics),
        'alert_count': len(firing_alerts),
        'activity_count': len(user_activities),
    }


async def aget_analytics_dashboard_by_date(
    date_from, date_to, user_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Fetch dashboard data within a date range in parallel.
    """
    tasks = [
        PerformanceMetric.aget_performance_summary(date_from, date_to),
        BusinessMetric.aget_by_name(
            metric_name="total_gmv", period_start=date_from, period_end=date_to
        ),
        Alert.aget_firing_alerts(limit=10),
        UserActivity.aget_analytics_summary(date_from, date_to),
    ]

    if user_id:
        tasks.append(UserActivity.aget_by_user(user_id, date_from, date_to, limit=50))

    results = await asyncio.gather(*tasks, return_exceptions=True)

    performance_summary = results[0] if not isinstance(results[0], Exception) else {}
    business_metrics = results[1] if not isinstance(results[1], Exception) else []
    firing_alerts = results[2] if not isinstance(results[2], Exception) else []
    activity_summary = results[3] if not isinstance(results[3], Exception) else {}
    user_activities = (
        results[4]
        if user_id and not isinstance(results[4], Exception)
        else []
    )

    return {
        'performance_summary': performance_summary,
        'business_metrics': business_metrics,
        'firing_alerts': firing_alerts,
        'activity_summary': activity_summary,
        'user_activities': user_activities,
        'performance_count': performance_summary.get('total_requests', 0),
        'business_count': len(business_metrics),
        'alert_count': len(firing_alerts),
        'activity_count': activity_summary.get('total_activities', 0),
    }


async def aget_realtime_analytics_summary(minutes: int = 5) -> Dict[str, Any]:
    """
    Fetch real-time analytics summary for the last N minutes in parallel.
    """
    since = timezone.now() - timedelta(minutes=minutes)

    tasks = [
        _acount_metric_since(since),
        _acount_performance_since(since),
        _acount_activity_since(since),
        _asum_slow_requests_since(since),
    ]

    results = await asyncio.gather(*tasks, return_exceptions=True)

    metric_count = results[0] if not isinstance(results[0], Exception) else 0
    request_count = results[1] if not isinstance(results[1], Exception) else 0
    activity_count = results[2] if not isinstance(results[2], Exception) else 0
    avg_response_time = results[3] if not isinstance(results[3], Exception) else 0

    return {
        'minutes': minutes,
        'metric_count': metric_count,
        'request_count': request_count,
        'activity_count': activity_count,
        'avg_response_time_ms': avg_response_time,
        'slow_request_count': 0,  # calculated inside _asum_slow_requests_since if needed
    }


async def _acount_metric_since(since):
    return await Metric.objects.filter(timestamp__gte=since).acount()


async def _acount_performance_since(since):
    return await PerformanceMetric.objects.filter(timestamp__gte=since).acount()


async def _acount_activity_since(since):
    return await UserActivity.objects.filter(timestamp__gte=since).acount()


async def _asum_slow_requests_since(since, threshold_ms: int = 500):
    from django.db.models import Avg

    result = await PerformanceMetric.objects.filter(
        timestamp__gte=since
    ).aaggregate(avg_response_time=Avg('response_time_ms'))
    return result.get('avg_response_time', 0)


async def aget_platform_health_summary() -> Dict[str, Any]:
    """
    Fetch a concise platform health summary in parallel.
    """
    from datetime import timedelta

    since = timezone.now() - timedelta(hours=1)

    tasks = [
        PerformanceMetric.aget_performance_summary(since, timezone.now()),
        Alert.aget_firing_alerts(limit=5),
        BusinessMetric.aget_recent_metrics(days=1, limit=5),
    ]

    results = await asyncio.gather(*tasks, return_exceptions=True)

    performance_summary = results[0] if not isinstance(results[0], Exception) else {}
    firing_alerts = results[1] if not isinstance(results[1], Exception) else []
    business_metrics = results[2] if not isinstance(results[2], Exception) else []

    total_requests = performance_summary.get('total_requests', 0)
    error_count = performance_summary.get('error_rate', 0)
    error_rate = (error_count / total_requests * 100) if total_requests else 0

    return {
        'health_status': 'healthy' if error_rate < 5 and not firing_alerts else 'degraded',
        'total_requests_1h': total_requests,
        'avg_response_time_ms': performance_summary.get('avg_response_time', 0),
        'error_rate_percent': error_rate,
        'firing_alerts_count': len(firing_alerts),
        'latest_business_metric': business_metrics[0] if business_metrics else None,
    }
