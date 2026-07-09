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
