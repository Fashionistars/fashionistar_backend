"""
Analytics Services for telemetry and performance monitoring.

Moved from apps/analytics/services.py (legacy root-level) to
apps/analytics/services/services.py for proper package structure.
Uses absolute imports instead of relative imports.
"""

import logging
import hashlib
import json
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from django.db.models import Count, Avg
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.conf import settings
from django.core.cache import cache

from apps.analytics.models import (
    Metric,
    UserActivity,
    PerformanceMetric,
    BusinessMetric,
    AlertRule,
    Alert,
)

logger = logging.getLogger(__name__)
User = get_user_model()


class AnalyticsService:
    """
    Main service to record and analyze system telemetry and business metrics with Redis caching.
    """

    def __init__(self):
        self.metrics_cache_ttl = getattr(settings, 'ANALYTICS_METRICS_CACHE_TTL', 300)
        self.business_cache_ttl = getattr(settings, 'ANALYTICS_BUSINESS_CACHE_TTL', 3600)
        self.cache_prefix = 'analytics:v1:'

    def _generate_cache_key(self, prefix: str, **kwargs) -> str:
        """Generate a unique cache key for analytics parameters."""
        cache_data = {k: str(v) if v is not None else None for k, v in sorted(kwargs.items())}
        cache_hash = hashlib.md5(json.dumps(cache_data, sort_keys=True).encode()).hexdigest()
        return f"{self.cache_prefix}{prefix}:{cache_hash}"

    def record_metric(self, name: str, value: float, metric_type: str = 'gauge',
                      tags: Optional[Dict[str, Any]] = None) -> Metric:
        """Record a numeric telemetry metric."""
        return Metric.objects.create(
            name=name,
            metric_type=metric_type,
            value=value,
            tags=tags or {}
        )

    def record_user_activity(self, user: User, action: str, resource: str = '',
                            resource_id: Optional[int] = None, metadata: Optional[Dict] = None,
                            request=None) -> UserActivity:
        """Record a user activity action."""
        activity_data = {
            'user': user,
            'action': action,
            'resource': resource,
            'resource_id': resource_id,
            'metadata': metadata or {}
        }

        if request:
            activity_data.update({
                'ip_address': self._get_client_ip(request),
                'user_agent': request.META.get('HTTP_USER_AGENT', ''),
                'session_id': request.session.session_key or ''
            })

        return UserActivity.objects.create(**activity_data)

    def record_performance_metric(self, endpoint: str, method: str, response_time_ms: int,
                                status_code: int, user: Optional[User] = None,
                                error_message: str = '', metadata: Optional[Dict] = None) -> PerformanceMetric:
        """Record an API endpoint performance entry."""
        return PerformanceMetric.objects.create(
            endpoint=endpoint,
            method=method,
            response_time_ms=response_time_ms,
            status_code=status_code,
            user=user,
            error_message=error_message,
            metadata=metadata or {}
        )

    def calculate_business_metrics(self, period_start: datetime, period_end: datetime) -> Dict[str, Any]:
        """Calculate key e-commerce order and activity metrics for a period."""
        try:
            from apps.order.models import Order
            total_orders = Order.objects.filter(
                created_at__range=[period_start, period_end]
            ).count()

            completed_orders = Order.objects.filter(
                created_at__range=[period_start, period_end],
                status='completed'
            ).count()
        except ImportError:
            total_orders = 0
            completed_orders = 0

        active_users = UserActivity.objects.filter(
            timestamp__range=[period_start, period_end]
        ).values('user').distinct().count()

        avg_response_time = PerformanceMetric.objects.filter(
            timestamp__range=[period_start, period_end]
        ).aggregate(avg_time=Avg('response_time_ms'))['avg_time'] or 0

        error_rate = PerformanceMetric.objects.filter(
            timestamp__range=[period_start, period_end],
            status_code__gte=400
        ).count()

        total_requests = PerformanceMetric.objects.filter(
            timestamp__range=[period_start, period_end]
        ).count()

        error_rate_percent = (error_rate / total_requests * 100) if total_requests > 0 else 0

        metrics = {
            'total_orders': total_orders,
            'completed_orders': completed_orders,
            'order_completion_rate': (completed_orders / total_orders * 100) if total_orders > 0 else 0,
            'active_users': active_users,
            'avg_response_time_ms': round(avg_response_time, 2),
            'error_rate_percent': round(error_rate_percent, 2),
            'total_api_requests': total_requests
        }

        for metric_name, value in metrics.items():
            BusinessMetric.objects.update_or_create(
                metric_name=metric_name,
                period_start=period_start,
                period_end=period_end,
                defaults={'value': value}
            )

        return metrics

    def get_user_analytics(self, user_id: Optional[Any] = None, days: int = 30) -> Dict[str, Any]:
        """Retrieve user activity and usage statistics with Redis caching."""
        cache_key = self._generate_cache_key('user_analytics', user_id=user_id, days=days)
        cached_result = cache.get(cache_key)
        if cached_result:
            return cached_result

        cutoff_date = timezone.now() - timedelta(days=days)

        queryset = UserActivity.objects.filter(timestamp__gte=cutoff_date)
        if user_id:
            queryset = queryset.filter(user_id=user_id)

        activity_breakdown = queryset.values('action').annotate(
            count=Count('id')
        ).order_by('-count')

        resource_usage = queryset.exclude(resource='').values('resource').annotate(
            count=Count('id')
        ).order_by('-count')[:10]

        daily_activity = queryset.extra(
            select={'day': "DATE(timestamp)"}
        ).values('day').annotate(
            count=Count('id')
        ).order_by('day')

        unique_users = queryset.values('user').distinct().count()
        total_activities = queryset.count()
        avg_activities_per_user = total_activities / unique_users if unique_users > 0 else 0

        result = {
            'period_days': days,
            'total_activities': total_activities,
            'unique_users': unique_users,
            'avg_activities_per_user': round(avg_activities_per_user, 2),
            'activity_breakdown': list(activity_breakdown),
            'resource_usage': list(resource_usage),
            'daily_activity': list(daily_activity)
        }

        cache.set(cache_key, result, self.metrics_cache_ttl)
        return result

    def get_performance_analytics(self, days: int = 7) -> Dict[str, Any]:
        """Retrieve API performance trends with Redis caching."""
        cache_key = self._generate_cache_key('performance_analytics', days=days)
        cached_result = cache.get(cache_key)
        if cached_result:
            return cached_result

        cutoff_date = timezone.now() - timedelta(days=days)

        metrics = PerformanceMetric.objects.filter(timestamp__gte=cutoff_date)

        total_requests = metrics.count()
        avg_response_time = metrics.aggregate(
            avg_time=Avg('response_time_ms')
        )['avg_time'] or 0

        status_breakdown = metrics.values('status_code').annotate(
            count=Count('id')
        ).order_by('status_code')

        slowest_endpoints = metrics.values('endpoint', 'method').annotate(
            avg_time=Avg('response_time_ms'),
            request_count=Count('id')
        ).order_by('-avg_time')[:10]

        errors = metrics.filter(status_code__gte=400)
        error_breakdown = errors.values('endpoint', 'status_code').annotate(
            count=Count('id')
        ).order_by('-count')[:10]

        response_times = list(metrics.values_list('response_time_ms', flat=True))
        response_times.sort()

        def percentile(data, p):
            if not data:
                return 0
            index = int(len(data) * p / 100)
            return data[min(index, len(data) - 1)]

        result = {
            'period_days': days,
            'total_requests': total_requests,
            'avg_response_time_ms': round(avg_response_time, 2),
            'p50_response_time_ms': percentile(response_times, 50),
            'p95_response_time_ms': percentile(response_times, 95),
            'p99_response_time_ms': percentile(response_times, 99),
            'status_breakdown': list(status_breakdown),
            'slowest_endpoints': list(slowest_endpoints),
            'error_breakdown': list(error_breakdown),
            'error_rate_percent': round((errors.count() / total_requests * 100) if total_requests > 0 else 0, 2)
        }

        cache.set(cache_key, result, self.metrics_cache_ttl)
        return result

    def check_alert_rules(self) -> List[Dict[str, Any]]:
        """Evaluate active alert rules against recent metrics."""
        triggered_alerts = []

        for rule in AlertRule.objects.filter(is_active=True):
            try:
                recent_metrics = Metric.objects.filter(
                    name=rule.metric_name,
                    timestamp__gte=timezone.now() - timedelta(minutes=5)
                )

                if not recent_metrics.exists():
                    continue

                latest_metric = recent_metrics.latest('timestamp')
                metric_value = latest_metric.value

                should_fire = False
                if rule.operator == 'gt' and metric_value > rule.threshold:
                    should_fire = True
                elif rule.operator == 'gte' and metric_value >= rule.threshold:
                    should_fire = True
                elif rule.operator == 'lt' and metric_value < rule.threshold:
                    should_fire = True
                elif rule.operator == 'lte' and metric_value <= rule.threshold:
                    should_fire = True
                elif rule.operator == 'eq' and metric_value == rule.threshold:
                    should_fire = True
                elif rule.operator == 'ne' and metric_value != rule.threshold:
                    should_fire = True

                if should_fire:
                    existing_alert = Alert.objects.filter(
                        rule=rule,
                        status='firing'
                    ).first()

                    if not existing_alert:
                        alert = Alert.objects.create(
                            rule=rule,
                            status='firing',
                            metric_value=metric_value,
                            message=f"{rule.name}: {rule.metric_name} is {metric_value} (threshold: {rule.threshold})",
                            metadata={
                                'metric_timestamp': latest_metric.timestamp.isoformat(),
                                'tags': latest_metric.tags
                            }
                        )

                        triggered_alerts.append({
                            'alert_id': alert.id,
                            'rule_name': rule.name,
                            'severity': rule.severity,
                            'message': alert.message,
                            'metric_value': metric_value,
                            'threshold': rule.threshold
                        })

                else:
                    Alert.objects.filter(
                        rule=rule,
                        status='firing'
                    ).update(
                        status='resolved',
                        resolved_at=timezone.now()
                    )

            except Exception as e:
                logger.error(f"Error checking alert rule {rule.name}: {str(e)}")
                continue

        return triggered_alerts

    def get_system_overview(self) -> Dict[str, Any]:
        """Retrieve a general summary of active e-commerce and performance telemetry with Redis caching."""
        cache_key = self._generate_cache_key('system_overview')
        cached_result = cache.get(cache_key)
        if cached_result:
            return cached_result

        now = timezone.now()
        last_24h = now - timedelta(hours=24)
        last_7d = now - timedelta(days=7)

        try:
            from apps.order.models import Order
            orders_24h = Order.objects.filter(created_at__gte=last_24h).count()
            orders_7d = Order.objects.filter(created_at__gte=last_7d).count()
        except ImportError:
            orders_24h = 0
            orders_7d = 0

        active_users_24h = UserActivity.objects.filter(
            timestamp__gte=last_24h
        ).values('user').distinct().count()

        avg_response_time_24h = PerformanceMetric.objects.filter(
            timestamp__gte=last_24h
        ).aggregate(avg_time=Avg('response_time_ms'))['avg_time'] or 0

        error_rate_24h = PerformanceMetric.objects.filter(
            timestamp__gte=last_24h,
            status_code__gte=400
        ).count()

        total_requests_24h = PerformanceMetric.objects.filter(
            timestamp__gte=last_24h
        ).count()

        error_rate_percent = (error_rate_24h / total_requests_24h * 100) if total_requests_24h > 0 else 0
        active_alerts = Alert.objects.filter(status='firing').count()

        result = {
            'orders_24h': orders_24h,
            'orders_7d': orders_7d,
            'active_users_24h': active_users_24h,
            'avg_response_time_24h_ms': round(avg_response_time_24h, 2),
            'error_rate_24h_percent': round(error_rate_percent, 2),
            'total_requests_24h': total_requests_24h,
            'active_alerts': active_alerts,
            'last_updated': now.isoformat()
        }

        cache.set(cache_key, result, self.metrics_cache_ttl)
        return result

    def _get_client_ip(self, request) -> Optional[str]:
        """Retrieve client IP address from request metadata."""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip


class MetricsService:
    """Minimal metrics service wrapper for backward compatibility."""

    def track_metric(self, user, metric_type: str, value: float, metadata=None):
        return Metric.objects.create(
            name=metric_type,
            metric_type='gauge',
            value=value,
            tags=metadata or {},
        )


class ReportingService:
    """Minimal reporting service wrapper for backward compatibility."""

    def get_user_metrics(self, user_id, start_date, end_date):
        count = Metric.objects.filter(timestamp__range=[start_date, end_date]).count()
        return {"total_metrics": count}


class RealTimeAnalyticsService:
    """
    Real-time analytics service for live dashboard updates and streaming metrics.
    Uses async methods for high-performance real-time data fetching.
    """

    def __init__(self):
        self.cache_prefix = 'analytics:realtime:v1:'
        self.cache_ttl = getattr(settings, 'ANALYTICS_REALTIME_CACHE_TTL', 60)

    def _generate_cache_key(self, prefix: str, **kwargs) -> str:
        """Generate a unique cache key for real-time analytics parameters."""
        cache_data = {k: v for k, v in sorted(kwargs.items())}
        cache_hash = hashlib.md5(json.dumps(cache_data, sort_keys=True).encode()).hexdigest()
        return f"{self.cache_prefix}{prefix}:{cache_hash}"

    async def aget_live_metrics(self, minutes: int = 5) -> Dict[str, Any]:
        """Get live metrics for the specified time window (async)."""
        cache_key = self._generate_cache_key('live_metrics', minutes=minutes)
        cached_result = cache.get(cache_key)
        if cached_result:
            return cached_result

        from datetime import timedelta
        since = timezone.now() - timedelta(minutes=minutes)

        performance_qs = PerformanceMetric.objects.filter(timestamp__gte=since)
        total_requests = await performance_qs.acount()

        if total_requests > 0:
            agg = await performance_qs.aaggregate(
                avg_time=Avg('response_time_ms'),
                p50_count=Count('id')
            )
            avg_response_time = agg['avg_time'] or 0
        else:
            avg_response_time = 0

        active_users = await UserActivity.objects.filter(
            timestamp__gte=since
        ).values('user').distinct().acount()

        firing_alerts = await Alert.objects.filter(status='firing').acount()

        result = {
            'time_window_minutes': minutes,
            'total_requests': total_requests,
            'avg_response_time_ms': round(avg_response_time, 2),
            'active_users': active_users,
            'firing_alerts': firing_alerts,
            'requests_per_minute': round(total_requests / minutes, 2) if minutes > 0 else 0,
            'timestamp': timezone.now().isoformat(),
        }

        cache.set(cache_key, result, self.cache_ttl)
        return result

    async def aget_live_user_activity(self, minutes: int = 5, limit: int = 20) -> List[Dict[str, Any]]:
        """Get live user activity feed (async)."""
        cache_key = self._generate_cache_key('live_activity', minutes=minutes, limit=limit)
        cached_result = cache.get(cache_key)
        if cached_result:
            return cached_result

        from datetime import timedelta
        since = timezone.now() - timedelta(minutes=minutes)

        activities = UserActivity.objects.filter(timestamp__gte=since).order_by('-timestamp')[:limit]
        activity_list = []

        async for activity in activities:
            activity_list.append({
                'id': activity.id,
                'action': activity.action,
                'resource': activity.resource,
                'resource_id': activity.resource_id,
                'timestamp': activity.timestamp.isoformat(),
            })

        cache.set(cache_key, activity_list, self.cache_ttl)
        return activity_list

    async def aget_live_performance_trend(self, minutes: int = 30, interval_minutes: int = 5) -> List[Dict[str, Any]]:
        """Get live performance trend data (async)."""
        cache_key = self._generate_cache_key('live_trend', minutes=minutes, interval=interval_minutes)
        cached_result = cache.get(cache_key)
        if cached_result:
            return cached_result

        from datetime import timedelta
        since = timezone.now() - timedelta(minutes=minutes)

        intervals = []
        current_time = timezone.now()

        for i in range(minutes // interval_minutes):
            interval_start = current_time - timedelta(minutes=(i + 1) * interval_minutes)
            interval_end = current_time - timedelta(minutes=i * interval_minutes)

            metrics = PerformanceMetric.objects.filter(
                timestamp__gte=interval_start,
                timestamp__lt=interval_end
            )

            count = await metrics.acount()
            if count > 0:
                agg = await metrics.aaggregate(avg_time=Avg('response_time_ms'))
                avg_time = agg['avg_time'] or 0
            else:
                avg_time = 0

            intervals.append({
                'interval_start': interval_start.isoformat(),
                'interval_end': interval_end.isoformat(),
                'request_count': count,
                'avg_response_time_ms': round(avg_time, 2),
            })

        intervals.reverse()
        cache.set(cache_key, intervals, self.cache_ttl)
        return intervals


realtime_analytics = RealTimeAnalyticsService()

