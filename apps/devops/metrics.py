# apps/devops/metrics.py
"""
DevOps metrics export for monitoring systems (Prometheus, Datadog, etc.).
Tracks deployment metrics, health check status, secret expiration, and environment status.
"""

import time
from typing import Dict, Any, Optional
from django.core.cache import cache
from django.conf import settings
from django.db.models import Count, Avg
from django.utils import timezone
from datetime import timedelta

from .models import EnvironmentConfig, SecretConfig, DeploymentHistory, HealthCheck, ServiceMonitoring


class DevOpsMetrics:
    """DevOps metrics collector and exporter."""

    def __init__(self):
        self.metrics_prefix = 'devops_'
        self.cache_ttl = getattr(settings, 'DEVOPS_METRICS_CACHE_TTL', 60)

    def get_deployment_metrics(self, days: int = 30) -> Dict[str, Any]:
        """
        Get deployment metrics for the specified time period.
        Returns deployment counts, success rates, and duration statistics.
        """
        since = timezone.now() - timedelta(days=days)
        queryset = DeploymentHistory.objects.filter(started_at__gte=since)

        total_deployments = queryset.count()
        if total_deployments == 0:
            return {
                'total_deployments': 0,
                'successful_deployments': 0,
                'failed_deployments': 0,
                'running_deployments': 0,
                'success_rate_percent': 0.0,
                'avg_duration_seconds': 0.0,
            }

        # Count by status
        successful = queryset.filter(status='success').count()
        failed = queryset.filter(status='failed').count()
        running = queryset.filter(status='running').count()

        # Average duration
        completed = queryset.filter(completed_at__isnull=False)
        durations = [(d.completed_at - d.started_at).total_seconds() for d in completed]
        avg_duration = sum(durations) / len(durations) if durations else 0.0

        return {
            'total_deployments': total_deployments,
            'successful_deployments': successful,
            'failed_deployments': failed,
            'running_deployments': running,
            'success_rate_percent': (successful / total_deployments * 100) if total_deployments > 0 else 0.0,
            'avg_duration_seconds': avg_duration,
        }

    def get_health_check_metrics(self, hours: int = 24) -> Dict[str, Any]:
        """
        Get health check metrics for the specified time period.
        Returns health check counts, response times, and status breakdown.
        """
        since = timezone.now() - timedelta(hours=hours)
        queryset = HealthCheck.objects.filter(checked_at__gte=since)

        total_checks = queryset.count()
        if total_checks == 0:
            return {
                'total_checks': 0,
                'healthy_checks': 0,
                'warning_checks': 0,
                'critical_checks': 0,
                'unknown_checks': 0,
                'avg_response_time_ms': 0.0,
                'health_rate_percent': 0.0,
            }

        # Count by status
        healthy = queryset.filter(status='healthy').count()
        warning = queryset.filter(status='warning').count()
        critical = queryset.filter(status='critical').count()
        unknown = queryset.filter(status='unknown').count()

        # Average response time
        response_times = queryset.filter(response_time__isnull=False).values_list('response_time', flat=True)
        avg_response_time = sum(response_times) / len(response_times) if response_times else 0.0

        return {
            'total_checks': total_checks,
            'healthy_checks': healthy,
            'warning_checks': warning,
            'critical_checks': critical,
            'unknown_checks': unknown,
            'avg_response_time_ms': avg_response_time,
            'health_rate_percent': (healthy / total_checks * 100) if total_checks > 0 else 0.0,
        }

    def get_secret_metrics(self) -> Dict[str, Any]:
        """
        Get secret metrics.
        Returns secret counts, expiration status, and category breakdown.
        """
        total_secrets = SecretConfig.objects.count()
        active_secrets = SecretConfig.objects.filter(is_active=True).count()

        # Expiration status
        now = timezone.now()
        warning_threshold = now + timedelta(days=7)
        expired = SecretConfig.objects.filter(expires_at__lte=now).count()
        expiring_soon = SecretConfig.objects.filter(
            expires_at__gt=now,
            expires_at__lte=warning_threshold
        ).count()

        # Category breakdown
        category_counts = {}
        for category in SecretConfig.CATEGORY_CHOICES:
            cat_name = category[0]
            count = SecretConfig.objects.filter(category=cat_name).count()
            category_counts[cat_name] = count

        return {
            'total_secrets': total_secrets,
            'active_secrets': active_secrets,
            'expired_secrets': expired,
            'expiring_soon_secrets': expiring_soon,
            'secrets_needing_attention': expired + expiring_soon,
            'category_counts': category_counts,
        }

    def get_environment_metrics(self) -> Dict[str, Any]:
        """
        Get environment metrics.
        Returns environment counts and status breakdown.
        """
        total_environments = EnvironmentConfig.objects.count()
        active_environments = EnvironmentConfig.objects.filter(is_active=True).count()

        # Environment type breakdown
        type_counts = {}
        for env_type in EnvironmentConfig.ENVIRONMENT_CHOICES:
            type_name = env_type[0]
            count = EnvironmentConfig.objects.filter(environment_type=type_name).count()
            type_counts[type_name] = count

        return {
            'total_environments': total_environments,
            'active_environments': active_environments,
            'inactive_environments': total_environments - active_environments,
            'type_counts': type_counts,
        }

    def get_service_monitoring_metrics(self) -> Dict[str, Any]:
        """
        Get service monitoring metrics.
        Returns monitoring counts and status breakdown.
        """
        total_monitoring = ServiceMonitoring.objects.count()
        active_monitoring = ServiceMonitoring.objects.filter(is_active=True).count()
        alert_enabled = ServiceMonitoring.objects.filter(alert_on_failure=True).count()

        # Service type breakdown
        type_counts = {}
        for service_type in ServiceMonitoring.SERVICE_TYPES:
            type_name = service_type[0]
            count = ServiceMonitoring.objects.filter(service_type=type_name).count()
            type_counts[type_name] = count

        return {
            'total_monitoring': total_monitoring,
            'active_monitoring': active_monitoring,
            'alert_enabled': alert_enabled,
            'type_counts': type_counts,
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

    def get_all_metrics(self, days: int = 30, hours: int = 24) -> Dict[str, Any]:
        """
        Get all devops metrics in a single call.
        Useful for dashboard and monitoring systems.
        """
        return {
            'deployments': self.get_deployment_metrics(days),
            'health_checks': self.get_health_check_metrics(hours),
            'secrets': self.get_secret_metrics(),
            'environments': self.get_environment_metrics(),
            'service_monitoring': self.get_service_monitoring_metrics(),
            'cache': self.get_cache_metrics(),
            'timestamp': timezone.now().isoformat(),
        }


# Singleton instance for easy import
devops_metrics = DevOpsMetrics()
