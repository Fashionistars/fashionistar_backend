# apps/analytics/metrics.py
"""
Analytics metrics export for monitoring systems (Prometheus, Datadog, etc.).
Tracks performance metrics, user activity, business metrics, and alert status.
"""

import time
from typing import Dict, Any, Optional
from django.core.cache import cache
from django.conf import settings
from django.db.models import Count, Avg
from django.utils import timezone
from datetime import timedelta

from .models import Metric, UserActivity, PerformanceMetric, BusinessMetric, Alert


class AnalyticsMetrics:
    """Analytics metrics collector and exporter."""

    def __init__(self):
        self.metrics_prefix = 'analytics_'
        self.cache_ttl = getattr(settings, 'ANALYTICS_METRICS_CACHE_TTL', 60)

    def get_performance_metrics(self, hours: int = 24) -> Dict[str, Any]:
        """
        Get performance metrics for the specified time period.
        Returns request counts, response times, and error rates.
        """
        since = timezone.now() - timedelta(hours=hours)
        queryset = PerformanceMetric.objects.filter(timestamp__gte=since)

        total_requests = queryset.count()
        if total_requests == 0:
            return {
                'total_requests': 0,
                'avg_response_time_ms': 0,
                'p50_response_time_ms': 0,
                'p95_response_time_ms': 0,
                'p99_response_time_ms': 0,
                'error_rate_percent': 0.0,
            }

        # Average response time
        avg_result = queryset.aggregate(avg_time=Avg('response_time_ms'))
        avg_response_time = avg_result['avg_time'] or 0

        # Percentiles (simplified - in production use proper percentile calculation)
        response_times = list(queryset.values_list('response_time_ms', flat=True).order_by('response_time_ms'))
        response_times.sort()
        
        p50 = response_times[len(response_times) // 2] if response_times else 0
        p95 = response_times[int(len(response_times) * 0.95)] if response_times else 0
        p99 = response_times[int(len(response_times) * 0.99)] if response_times else 0

        # Error rate
        error_count = queryset.filter(status_code__gte=400).count()
        error_rate = (error_count / total_requests * 100) if total_requests > 0 else 0.0

        return {
            'total_requests': total_requests,
            'avg_response_time_ms': avg_response_time,
            'p50_response_time_ms': p50,
            'p95_response_time_ms': p95,
            'p99_response_time_ms': p99,
            'error_rate_percent': error_rate,
        }

    def get_user_activity_metrics(self, hours: int = 24) -> Dict[str, Any]:
        """
        Get user activity metrics for the specified time period.
        Returns activity counts, unique users, and action breakdown.
        """
        since = timezone.now() - timedelta(hours=hours)
        queryset = UserActivity.objects.filter(timestamp__gte=since)

        total_activities = queryset.count()
        unique_users = queryset.values('user').distinct().count()

        # Action breakdown
        action_breakdown = queryset.values('action').annotate(
            count=Count('id')
        ).order_by('-count')

        return {
            'total_activities': total_activities,
            'unique_users': unique_users,
            'avg_activities_per_user': total_activities / unique_users if unique_users > 0 else 0,
            'action_breakdown': list(action_breakdown),
        }

    def get_business_metrics(self, days: int = 30) -> Dict[str, Any]:
        """
        Get business metrics for the specified time period.
        Returns business KPIs and aggregates.
        """
        since = timezone.now() - timedelta(days=days)
        queryset = BusinessMetric.objects.filter(created_at__gte=since)

        metrics_by_name = {}
        async for metric in queryset:
            if metric.metric_name not in metrics_by_name:
                metrics_by_name[metric.metric_name] = []
            metrics_by_name[metric.metric_name].append(metric.value)

        # Calculate averages for each metric name
        averaged_metrics = {}
        for name, values in metrics_by_name.items():
            if values:
                averaged_metrics[name] = sum(values) / len(values)

        return {
            'period_days': days,
            'metric_count': queryset.count(),
            'metrics_by_name': averaged_metrics,
        }

    def get_alert_metrics(self) -> Dict[str, Any]:
        """
        Get alert status metrics.
        Returns firing alerts, resolved alerts, and alert counts by severity.
        """
        firing_alerts = Alert.objects.filter(status='firing').count()
        resolved_alerts = Alert.objects.filter(status='resolved').count()
        total_alerts = Alert.objects.count()

        # Alert count by severity (through AlertRule)
        from django.db.models import F
        severity_breakdown = Alert.objects.values(
            'rule__severity'
        ).annotate(
            count=Count('id')
        )

        return {
            'firing_alerts': firing_alerts,
            'resolved_alerts': resolved_alerts,
            'total_alerts': total_alerts,
            'severity_breakdown': list(severity_breakdown),
        }

    def get_cache_metrics(self) -> Dict[str, Any]:
        """
        Get cache performance metrics.
        Returns cache hit rate and cache size statistics.
        """
        # Cache hit rate (estimated from recent operations)
        cache_hits_key = f"{self.metrics_prefix}cache_hits"
        cache_misses_key = f"{self.metrics_prefix}cache_misses"
        
        hits = cache.get(cache_hits_key, 0)
        misses = cache.get(cache_misses_key, 0)
        total = hits + misses
        
        cache_hit_rate = hits / total if total > 0 else 0.0

        return {
            'cache_hits': hits,
            'cache_misses': misses,
            'cache_hit_rate': cache_hit_rate,
            'total_cache_operations': total,
        }

    def record_cache_hit(self):
        """Record a cache hit event."""
        cache_hits_key = f"{self.metrics_prefix}cache_hits"
        current = cache.get(cache_hits_key, 0)
        cache.set(cache_hits_key, current + 1, self.cache_ttl)

    def record_cache_miss(self):
        """Record a cache miss event."""
        cache_misses_key = f"{self.metrics_prefix}cache_misses"
        current = cache.get(cache_misses_key, 0)
        cache.set(cache_misses_key, current + 1, self.cache_ttl)

    def get_all_metrics(self, hours: int = 24, days: int = 30) -> Dict[str, Any]:
        """
        Get all analytics metrics in a single call.
        Useful for dashboard and monitoring systems.
        """
        return {
            'performance': self.get_performance_metrics(hours),
            'user_activity': self.get_user_activity_metrics(hours),
            'business': self.get_business_metrics(days),
            'alerts': self.get_alert_metrics(),
            'cache': self.get_cache_metrics(),
            'timestamp': timezone.now().isoformat(),
        }


# Singleton instance for easy import
analytics_metrics = AnalyticsMetrics()
